from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from accounts.mixins import PerfilRequiredMixin
from accounts.models import Usuario

from .forms import AgendamentoForm
from .models import Agendamento, Categoria, Profissional, Servico

Perfil = Usuario.Perfil
Status = Agendamento.Status



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
        ctx["profissionais"] = Profissional.objects.filter(ativo=True).select_related("usuario")
        return ctx

class ClienteAgendamentosView(PerfilRequiredMixin, ListView):
    perfis = (Perfil.CLIENTE,)
    template_name = "salao/cliente_lista.html"
    context_object_name = "agendamentos"
    paginate_by = 10

    def get_queryset(self):
        qs = Agendamento.objects.filter(cliente=self.request.user).select_related(
            "profissional__usuario", "servico"
        )
        status = self.request.GET.get("status")
        if status in Status.values:
            qs = qs.filter(status=status)
        return qs.order_by("-data_hora")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = Status.choices
        ctx["status_atual"] = self.request.GET.get("status", "")
        return ctx


class AgendamentoCreateView(PerfilRequiredMixin, CreateView):
    perfis = (Perfil.CLIENTE,)
    form_class = AgendamentoForm
    template_name = "salao/agendamento_form.html"
    success_url = reverse_lazy("cliente_agendamentos")

    def form_valid(self, form):
        form.instance.cliente = self.request.user
        messages.success(self.request, "Agendamento solicitado! Aguarde a confirmação do salão.")
        return super().form_valid(form)


class AgendamentoCancelarView(PerfilRequiredMixin, View):
    perfis = (Perfil.CLIENTE,)

    def post(self, request, pk):
        ag = get_object_or_404(Agendamento, pk=pk, cliente=request.user)
        if ag.pode_cancelar:
            ag.status = Status.CANCELADO
            ag.save(update_fields=["status"])
            messages.success(request, "Agendamento cancelado.")
        else:
            messages.error(request, "Este agendamento não pode mais ser cancelado.")
        return redirect("cliente_agendamentos")


class ServicosDoProfissionalAPI(PerfilRequiredMixin, View):
    """JSON com os serviços de um profissional (usado no formulário de agendamento)."""

    perfis = (Perfil.CLIENTE,)

    def get(self, request, pk):
        prof = get_object_or_404(Profissional, pk=pk, ativo=True)
        dados = [
            {"id": s.pk, "nome": s.nome, "preco": str(s.preco), "duracao": s.duracao_min}
            for s in prof.servicos.filter(ativo=True)
        ]
        return JsonResponse(dados, safe=False)



class AgendaProfissionalView(PerfilRequiredMixin, ListView):
    perfis = (Perfil.PROFISSIONAL,)
    template_name = "salao/prof_agenda.html"
    context_object_name = "agendamentos"

    def get_dia(self):
        try:
            return date.fromisoformat(self.request.GET.get("data", ""))
        except ValueError:
            return timezone.localdate()

    def get_queryset(self):
        self.profissional = Profissional.objects.filter(usuario=self.request.user).first()
        self.dia = self.get_dia()
        if not self.profissional:
            return Agendamento.objects.none()
        return (
            Agendamento.objects.filter(profissional=self.profissional, data_hora__date=self.dia)
            .select_related("cliente", "servico")
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

        qs = Agendamento.objects.filter(data_hora__date__gte=inicio, data_hora__date__lte=fim)
        ativos = qs.exclude(status=Status.CANCELADO)

        por_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
        ctx.update(
            inicio=inicio,
            fim=fim,
            total=qs.count(),
            faturamento=qs.filter(status=Status.CONCLUIDO).aggregate(t=Sum("preco_cobrado"))["t"] or 0,
            previsto=ativos.filter(status__in=[Status.PENDENTE, Status.CONFIRMADO]).aggregate(
                t=Sum("preco_cobrado")
            )["t"] or 0,
            status_resumo=[(label, por_status.get(valor, 0)) for valor, label in Status.choices],
            top_servicos=ativos.values("servico__nome")
            .annotate(n=Count("id"), receita=Sum("preco_cobrado"))
            .order_by("-n")[:5],
            por_profissional=ativos.values(
                "profissional__usuario__first_name", "profissional__usuario__username"
            )
            .annotate(n=Count("id"), receita=Sum("preco_cobrado"))
            .order_by("-n"),
            proximos=Agendamento.objects.filter(
                data_hora__gte=timezone.now(), status__in=[Status.PENDENTE, Status.CONFIRMADO]
            ).select_related("cliente", "profissional__usuario", "servico")[:5],
        )
        return ctx
