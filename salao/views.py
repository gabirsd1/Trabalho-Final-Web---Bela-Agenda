from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from accounts.mixins import PerfilRequiredMixin
from accounts.models import Usuario

from .forms import AgendamentoForm, AvaliacaoForm, GerarHorariosForm, PerfilProfissionalForm
from .models import Agendamento, Avaliacao, Categoria, HorarioDisponivel, Profissional, Servico

Perfil = Usuario.Perfil
Status = Agendamento.Status

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
DIAS_SEMANA_LONGO = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def rotulo_dia(d):
    return f"{DIAS_SEMANA[d.weekday()]}, {d:%d/%m}"


def profissionais_com_nota():
    """Profissionais ativos já com a média e o total de avaliações calculados."""
    return (
        Profissional.objects.filter(ativo=True)
        .select_related("usuario")
        .annotate(
            media=Avg("agendamentos__avaliacao__nota"),
            n_aval=Count("agendamentos__avaliacao", distinct=True),
        )
    )


# ───────────────────────────── público ─────────────────────────────


class HomeView(TemplateView):
    template_name = "salao/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = (
            Categoria.objects.filter(servicos__ativo=True)
            .distinct()
            .prefetch_related(
                Prefetch("servicos", queryset=Servico.objects.filter(ativo=True), to_attr="servicos_ativos")
            )
        )
        ctx["profissionais"] = profissionais_com_nota()
        return ctx


class ProfissionalDetalheView(DetailView):
    """Perfil público: apresentação, serviços, avaliações e próximos horários livres."""

    template_name = "salao/profissional_detalhe.html"
    context_object_name = "prof"

    def get_queryset(self):
        return Profissional.objects.filter(ativo=True).select_related("usuario")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        prof = self.object
        avaliacoes = Avaliacao.objects.filter(agendamento__profissional=prof)
        resumo = avaliacoes.aggregate(media=Avg("nota"), total=Count("id"))
        por_nota = {r["nota"]: r["n"] for r in avaliacoes.values("nota").annotate(n=Count("id"))}
        total = resumo["total"] or 0
        ctx.update(
            servicos=prof.servicos.filter(ativo=True).select_related("categoria"),
            media=resumo["media"],
            total_aval=total,
            distribuicao=[
                {"nota": n, "qtd": por_nota.get(n, 0), "pct": round(por_nota.get(n, 0) * 100 / total) if total else 0}
                for n in (5, 4, 3, 2, 1)
            ],
            avaliacoes=avaliacoes.select_related("agendamento__cliente", "agendamento__servico")[:8],
            proximos=prof.horarios.futuros().livres()[:8],
            atendimentos=prof.agendamentos.filter(status=Status.CONCLUIDO).count(),
        )
        return ctx


# ───────────────────────────── cliente ─────────────────────────────


class ClienteAgendamentosView(PerfilRequiredMixin, ListView):
    perfis = (Perfil.CLIENTE,)
    template_name = "salao/cliente_lista.html"
    context_object_name = "agendamentos"
    paginate_by = 10

    def get_queryset(self):
        qs = Agendamento.objects.filter(cliente=self.request.user).select_related(
            "profissional__usuario", "servico", "avaliacao"
        )
        status = self.request.GET.get("status")
        if status in Status.values:
            qs = qs.filter(status=status)
        return qs.order_by("-data_hora")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = Status.choices
        ctx["status_atual"] = self.request.GET.get("status", "")
        ctx["para_avaliar"] = Agendamento.objects.filter(
            cliente=self.request.user, status=Status.CONCLUIDO, avaliacao__isnull=True
        ).count()
        return ctx


class AgendamentoCreateView(PerfilRequiredMixin, CreateView):
    perfis = (Perfil.CLIENTE,)
    form_class = AgendamentoForm
    template_name = "salao/agendamento_form.html"
    success_url = reverse_lazy("cliente_agendamentos")

    def get_initial(self):
        inicial = super().get_initial()
        prof = self.request.GET.get("profissional")
        if prof and prof.isdigit():
            inicial["profissional"] = int(prof)
        return inicial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["profissionais"] = profissionais_com_nota()
        return ctx

    def form_valid(self, form):
        form.instance.cliente = self.request.user
        messages.success(self.request, "Agendamento solicitado! Aguarde a confirmação do profissional.")
        return super().form_valid(form)


class AgendamentoCancelarView(PerfilRequiredMixin, View):
    perfis = (Perfil.CLIENTE,)

    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk, cliente=request.user)
        if ag.pode_cancelar:
            ag.status = Status.CANCELADO
            ag.save(update_fields=["status"])
            messages.success(request, "Agendamento cancelado. O horário voltou a ficar disponível.")
        else:
            messages.error(request, "Este agendamento não pode mais ser cancelado.")
        return redirect("cliente_agendamentos")


class AvaliarAgendamentoView(PerfilRequiredMixin, CreateView):
    perfis = (Perfil.CLIENTE,)
    form_class = AvaliacaoForm
    template_name = "salao/avaliar_form.html"
    success_url = reverse_lazy("cliente_agendamentos")

    def get_agendamento(self):
        if not hasattr(self, "_ag"):
            self._ag = get_object_or_404(
                Agendamento.objects.select_related("profissional__usuario", "servico"),
                pk=self.kwargs["pk"],
                cliente=self.request.user,
            )
        return self._ag

    def get(self, request, *args, **kwargs):
        return self._checar() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self._checar() or super().post(request, *args, **kwargs)

    def _checar(self):
        ag = self.get_agendamento()
        if ag.status != Status.CONCLUIDO:
            messages.error(self.request, "Você só pode avaliar atendimentos concluídos.")
            return redirect("cliente_agendamentos")
        if ag.avaliacao_feita:
            messages.info(self.request, "Você já avaliou este atendimento. Obrigada!")
            return redirect("cliente_agendamentos")
        return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["agendamento"] = self.get_agendamento()
        ctx["notas_invertidas"] = list(reversed(Avaliacao.NOTAS))
        return ctx

    def form_valid(self, form):
        form.instance.agendamento = self.get_agendamento()
        messages.success(self.request, "Avaliação enviada. Obrigada por ajudar outros clientes!")
        return super().form_valid(form)


class ServicosDoProfissionalAPI(PerfilRequiredMixin, View):
    """JSON com os serviços de um profissional (usado no formulário de agendamento)."""

    perfis = (Perfil.CLIENTE,)

    def get(self, request, pk):
        prof = get_object_or_404(Profissional, pk=pk, ativo=True)
        dados = [
            {
                "id": s.pk,
                "nome": s.nome,
                "categoria": s.categoria.nome,
                "preco": str(s.preco),
                "duracao": s.duracao_min,
            }
            for s in prof.servicos.filter(ativo=True).select_related("categoria")
        ]
        return JsonResponse(dados, safe=False)


class HorariosDoProfissionalAPI(PerfilRequiredMixin, View):
    """JSON com os horários livres, agrupados por dia, que comportam o serviço escolhido."""

    perfis = (Perfil.CLIENTE,)

    def get(self, request, pk):
        prof = get_object_or_404(Profissional, pk=pk, ativo=True)
        duracao = 0
        servico = request.GET.get("servico", "")
        if servico.isdigit():
            duracao = get_object_or_404(prof.servicos, pk=int(servico)).duracao_min

        dias = {}
        for h in prof.horarios.futuros().livres():
            if h.duracao_min < duracao:
                continue
            ini = timezone.localtime(h.inicio)
            dia = dias.setdefault(
                ini.date(), {"data": ini.date().isoformat(), "rotulo": rotulo_dia(ini.date()), "horarios": []}
            )
            dia["horarios"].append(
                {"id": h.pk, "hora": f"{ini:%H:%M}", "fim": f"{timezone.localtime(h.fim):%H:%M}"}
            )
        return JsonResponse({"dias": list(dias.values())})


# ─────────────────────────── profissional ───────────────────────────


class ProfissionalMixin(PerfilRequiredMixin):
    perfis = (Perfil.PROFISSIONAL,)

    def get_profissional(self):
        if not hasattr(self, "_prof"):
            self._prof = Profissional.objects.filter(usuario=self.request.user).first()
        return self._prof


class AgendaProfissionalView(ProfissionalMixin, ListView):
    template_name = "salao/prof_agenda.html"
    context_object_name = "agendamentos"

    def get_dia(self):
        try:
            return date.fromisoformat(self.request.GET.get("data", ""))
        except ValueError:
            return timezone.localdate()

    def get_queryset(self):
        self.profissional = self.get_profissional()
        self.dia = self.get_dia()
        if not self.profissional:
            return Agendamento.objects.none()
        return (
            Agendamento.objects.filter(profissional=self.profissional, data_hora__date=self.dia)
            .select_related("cliente", "servico", "avaliacao")
            .order_by("data_hora")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            profissional=self.profissional,
            dia=self.dia,
            dia_anterior=self.dia - timedelta(days=1),
            dia_seguinte=self.dia + timedelta(days=1),
            eh_hoje=self.dia == timezone.localdate(),
        )
        if self.profissional:
            hoje = timezone.localdate()
            meus = Agendamento.objects.filter(profissional=self.profissional)
            ativos = meus.exclude(status=Status.CANCELADO)
            media, total = self.profissional.resumo_avaliacoes()
            ctx["resumo"] = {
                "hoje": ativos.filter(data_hora__date=hoje).count(),
                "pendentes": meus.filter(status=Status.PENDENTE, data_hora__gte=timezone.now()).count(),
                "semana": ativos.filter(
                    data_hora__gte=timezone.now(), data_hora__lt=timezone.now() + timedelta(days=7)
                ).count(),
                "livres": self.profissional.horarios.futuros().livres().count(),
                "media": media,
                "total_aval": total,
            }
        return ctx


class AgendamentoAcaoView(PerfilRequiredMixin, View):
    """Profissional confirma, conclui ou cancela os próprios atendimentos."""

    perfis = (Perfil.PROFISSIONAL,)

    ACOES = {
        "confirmar": ({Status.PENDENTE}, Status.CONFIRMADO),
        "concluir": ({Status.CONFIRMADO}, Status.CONCLUIDO),
        "cancelar": ({Status.PENDENTE, Status.CONFIRMADO}, Status.CANCELADO),
    }

    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk, profissional__usuario=request.user)
        origem, novo = self.ACOES.get(request.POST.get("acao"), (set(), None))
        if novo and ag.status in origem:
            ag.status = novo
            ag.save(update_fields=["status"])
            messages.success(request, f"Atendimento marcado como {ag.get_status_display().lower()}.")
        else:
            messages.error(request, "Ação não permitida para o status atual.")
        dia = timezone.localtime(ag.data_hora).date().isoformat()
        return redirect(f"{reverse('prof_agenda')}?data={dia}")


class ProfissionalHorariosView(ProfissionalMixin, FormView):
    """O profissional cadastra e remove os horários que os clientes poderão escolher."""

    form_class = GerarHorariosForm
    template_name = "salao/prof_horarios.html"
    success_url = reverse_lazy("prof_horarios")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        prof = self.get_profissional()
        ctx["profissional"] = prof
        grupos = {}
        if prof:
            horarios = (
                prof.horarios.futuros()
                .filter(inicio__lt=timezone.now() + timedelta(days=45))
                .annotate(reservas=Count("agendamentos", filter=~Q(agendamentos__status="CANC")))
            )
            for h in horarios:
                d = timezone.localtime(h.inicio).date()
                grupos.setdefault(d, []).append(h)
        ctx["grupos"] = [(d, rotulo_dia(d), hs) for d, hs in grupos.items()]
        ctx["total_livres"] = sum(1 for hs in grupos.values() for h in hs if not h.reservas)
        return ctx

    def form_valid(self, form):
        prof = self.get_profissional()
        if not prof:
            messages.error(self.request, "Seu usuário ainda não foi vinculado a um cadastro de profissional.")
            return redirect("prof_horarios")
        criados = pulados = 0
        for inicio, fim in form.blocos():
            existe = HorarioDisponivel.objects.filter(
                profissional=prof, inicio__lt=fim, fim__gt=inicio
            ).exists()
            if existe:
                pulados += 1
            else:
                HorarioDisponivel.objects.create(profissional=prof, inicio=inicio, fim=fim)
                criados += 1
        if criados:
            texto = f"{criados} horário(s) cadastrado(s)."
            if pulados:
                texto += f" {pulados} já existia(m) e foi(ram) ignorado(s)."
            messages.success(self.request, texto)
        else:
            messages.warning(
                self.request, "Nenhum horário novo foi criado: todos já existiam ou já passaram."
            )
        return super().form_valid(form)


class HorarioExcluirView(PerfilRequiredMixin, View):
    perfis = (Perfil.PROFISSIONAL,)

    def post(self, request, pk):
        h = get_object_or_404(HorarioDisponivel, pk=pk, profissional__usuario=request.user)
        if h.reservado:
            messages.error(request, "Este horário já tem um agendamento. Cancele o atendimento antes.")
        else:
            h.delete()
            messages.success(request, "Horário removido.")
        return redirect("prof_horarios")


class ProfissionalPerfilView(ProfissionalMixin, UpdateView):
    form_class = PerfilProfissionalForm
    template_name = "salao/prof_perfil_form.html"
    success_url = reverse_lazy("prof_perfil")

    def get_object(self, queryset=None):
        return get_object_or_404(Profissional, usuario=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Perfil atualizado. Ele já aparece para os clientes.")
        return super().form_valid(form)


# ───────────────────────────── administração ─────────────────────────────


class GestaoPainelView(PerfilRequiredMixin, TemplateView):
    perfis = (Perfil.ADMIN,)
    template_name = "salao/gestao_painel.html"

    def _data(self, nome, padrao):
        try:
            return date.fromisoformat(self.request.GET.get(nome, ""))
        except ValueError:
            return padrao

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        inicio = self._data("inicio", hoje.replace(day=1))
        fim = self._data("fim", hoje)
        if inicio > fim:
            inicio, fim = fim, inicio
        if (fim - inicio).days > 365:
            inicio = fim - timedelta(days=365)

        qs = Agendamento.objects.filter(data_hora__date__gte=inicio, data_hora__date__lte=fim)
        ativos = qs.exclude(status=Status.CANCELADO)
        concluidos = qs.filter(status=Status.CONCLUIDO)
        abertos = qs.filter(status__in=[Status.PENDENTE, Status.CONFIRMADO])

        total = qs.count()
        n_concluidos = concluidos.count()
        n_cancelados = qs.filter(status=Status.CANCELADO).count()
        faturamento = concluidos.aggregate(t=Sum("preco_cobrado"))["t"] or 0
        previsto = abertos.aggregate(t=Sum("preco_cobrado"))["t"] or 0

        aval = Avaliacao.objects.filter(
            agendamento__data_hora__date__gte=inicio, agendamento__data_hora__date__lte=fim
        )
        resumo_aval = aval.aggregate(media=Avg("nota"), total=Count("id"))

        # série diária para o gráfico (concluído x a receber)
        por_dia = {}
        for linha in (
            qs.exclude(status=Status.CANCELADO)
            .annotate(d=TruncDate("data_hora"))
            .values("d", "status")
            .annotate(t=Sum("preco_cobrado"))
        ):
            chave = linha["d"]
            atual = por_dia.setdefault(chave, {"conc": 0.0, "prev": 0.0})
            atual["conc" if linha["status"] == Status.CONCLUIDO else "prev"] += float(linha["t"] or 0)
        dias, conc, prev = [], [], []
        d = inicio
        while d <= fim:
            dias.append(f"{d:%d/%m}")
            conc.append(round(por_dia.get(d, {}).get("conc", 0.0), 2))
            prev.append(round(por_dia.get(d, {}).get("prev", 0.0), 2))
            d += timedelta(days=1)

        por_status = {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))}
        top_servicos = list(
            ativos.values("servico__nome")
            .annotate(n=Count("id"), receita=Sum("preco_cobrado"))
            .order_by("-n", "servico__nome")[:6]
        )

            # ── relatórios por profissional ──
        # "Atendimento" = serviço concluído; o que ainda vai acontecer entra em "a receber".
        notas = {
            r["agendamento__profissional"]: r
            for r in Avaliacao.objects.values("agendamento__profissional").annotate(
                media=Avg("nota"), n=Count("id")
            )
        }

        def linha_prof(pk, nome, r=None):
            r = r or {}
            concl = r.get("concluidos") or 0
            receita = r.get("receita") or 0
            nota = notas.get(pk, {})
            return {
                "id": pk,
                "nome": nome,
                "concluidos": concl,
                "n": concl,  # nome antigo, mantido por compatibilidade
                "receita": receita,
                "a_receber": r.get("a_receber") or 0,
                "cancelados": r.get("cancelados") or 0,
                "total": r.get("total") or 0,
                "ticket": (receita / concl) if concl else 0,
                "pct": round(receita * 100 / faturamento) if faturamento else 0,
                "media": nota.get("media"),
                "n_aval": nota.get("n", 0),
            }

        linhas = {}
        for r in qs.values(
            "profissional", "profissional__usuario__first_name", "profissional__usuario__username"
        ).annotate(
            concluidos=Count("id", filter=Q(status=Status.CONCLUIDO)),
            receita=Sum("preco_cobrado", filter=Q(status=Status.CONCLUIDO)),
            a_receber=Sum("preco_cobrado", filter=Q(status__in=[Status.PENDENTE, Status.CONFIRMADO])),
            cancelados=Count("id", filter=Q(status=Status.CANCELADO)),
            total=Count("id"),
        ):
            nome = r["profissional__usuario__first_name"] or r["profissional__usuario__username"]
            linhas[r["profissional"]] = linha_prof(r["profissional"], nome, r)
        # quem está ativo mas não teve movimento no período também aparece (com zeros)
        for prof in Profissional.objects.filter(ativo=True).select_related("usuario"):
            linhas.setdefault(prof.pk, linha_prof(prof.pk, prof.usuario.first_name or prof.usuario.username))
        ranking = sorted(linhas.values(), key=lambda x: (-x["concluidos"], -x["receita"], x["nome"].lower()))

        mais_atend = max((x for x in ranking if x["concluidos"]), key=lambda x: (x["concluidos"], x["receita"]), default=None)
        mais_fat = max((x for x in ranking if x["receita"]), key=lambda x: x["receita"], default=None)
        servico_rende = (
            concluidos.values("servico__nome")
            .annotate(receita=Sum("preco_cobrado"), n=Count("id"))
            .order_by("-receita", "servico__nome")
            .first()
        )

        # movimento por dia da semana e por horário (agendamentos não cancelados)
        por_semana = [0] * 7
        for r in ativos.annotate(dow=ExtractWeekDay("data_hora")).values("dow").annotate(n=Count("id")):
            por_semana[(r["dow"] + 5) % 7] += r["n"]  # Django: 1 = domingo → nosso 0 = segunda
        por_hora = {
            r["h"]: r["n"] for r in ativos.annotate(h=ExtractHour("data_hora")).values("h").annotate(n=Count("id"))
        }
        dia_pico = hora_pico = None
        if any(por_semana):
            i = por_semana.index(max(por_semana))
            dia_pico = {"nome": DIAS_SEMANA_LONGO[i].capitalize() + ("-feira" if i < 5 else ""), "n": por_semana[i]}
        if por_hora:
            h = min(por_hora, key=lambda k: (-por_hora[k], k))
            hora_pico = {"rotulo": f"{h:02d}h", "n": por_hora[h]}

        top_clientes = [
            {
                "nome": f"{r['cliente__first_name']} {r['cliente__last_name']}".strip() or r["cliente__username"],
                "n": r["n"],
                "gasto": r["gasto"] or 0,
            }
            for r in concluidos.values("cliente", "cliente__first_name", "cliente__last_name", "cliente__username")
            .annotate(n=Count("id"), gasto=Sum("preco_cobrado"))
            .order_by("-gasto", "-n", "cliente__username")[:5]
        ]
        por_receita = sorted(
            (x for x in ranking if x["receita"] or x["a_receber"]),
            key=lambda x: (-(x["receita"] + x["a_receber"]), x["nome"].lower()),
        )

        def atalho(rotulo, ini, fi):
            return {"rotulo": rotulo, "inicio": ini, "fim": fi, "ativo": (ini, fi) == (inicio, fim)}

        ctx.update(
            inicio=inicio,
            fim=fim,
            atalhos=[
                atalho("Últimos 7 dias", hoje - timedelta(days=6), hoje),
                atalho("Últimos 30 dias", hoje - timedelta(days=29), hoje),
                atalho("Este mês", hoje.replace(day=1), hoje),
            ],
            total=total,
            n_concluidos=n_concluidos,
            n_cancelados=n_cancelados,
            taxa_cancelamento=round(n_cancelados * 100 / total) if total else 0,
            faturamento=faturamento,
            previsto=previsto,
            ticket_medio=(faturamento / n_concluidos) if n_concluidos else 0,
            clientes=ativos.values("cliente").distinct().count(),
            nota_media=resumo_aval["media"],
            total_aval=resumo_aval["total"],
            horarios_livres=HorarioDisponivel.objects.futuros().livres().count(),
            status_resumo=[(label, por_status.get(valor, 0)) for valor, label in Status.choices],
            top_servicos=top_servicos,
                      ranking=ranking,
            destaques={
                "mais_atend": mais_atend,
                "mais_fat": mais_fat,
                "servico_rende": servico_rende,
                "dia_pico": dia_pico,
                "hora_pico": hora_pico,
            },
            top_clientes=top_clientes,
            ultimas_avaliacoes=Avaliacao.objects.select_related(
                "agendamento__cliente", "agendamento__profissional__usuario", "agendamento__servico"
            )[:4],
            proximos=Agendamento.objects.filter(
                data_hora__gte=timezone.now(), status__in=[Status.PENDENTE, Status.CONFIRMADO]
            ).select_related("cliente", "profissional__usuario", "servico")[:6],
            grafico={
                "dias": dias,
                "concluido": conc,
                "previsto": prev,
                "status": {
                    "rotulos": [label for _, label in Status.choices],
                    "valores": [por_status.get(valor, 0) for valor, _ in Status.choices],
                },
                              "servicos": {
                    "rotulos": [s["servico__nome"] for s in top_servicos],
                    "valores": [s["n"] for s in top_servicos],
                },
                "profissionais": {
                    "rotulos": [x["nome"] for x in por_receita],
                    "concluido": [float(x["receita"]) for x in por_receita],
                    "a_receber": [float(x["a_receber"]) for x in por_receita],
                },
                "semana": {"rotulos": DIAS_SEMANA[:6], "valores": por_semana[:6]},
            },
        )
        return ctx
