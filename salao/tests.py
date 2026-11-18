from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario

from .models import Agendamento, Avaliacao, Categoria, HorarioDisponivel, Profissional, Servico

P = Usuario.Perfil
S = Agendamento.Status


def proximo_horario(hora=10, dias=2):
    """Próximo dia útil (seg–sáb) no futuro, na hora indicada."""
    d = timezone.localtime().replace(hour=hora, minute=0, second=0, microsecond=0) + timedelta(days=dias)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Categoria.objects.create(nome="Cabelo")
        cls.corte = Servico.objects.create(categoria=cat, nome="Corte", preco=Decimal("50"), duracao_min=60)
        cls.barba = Servico.objects.create(categoria=cat, nome="Barba", preco=Decimal("30"), duracao_min=30)
        cls.admin = Usuario.objects.create_user("admin", password="x", perfil=P.ADMIN)
        cls.u_prof = Usuario.objects.create_user("ana", password="x", perfil=P.PROFISSIONAL, first_name="Ana")
        cls.cliente = Usuario.objects.create_user("maria", password="x", perfil=P.CLIENTE, first_name="Maria")
        cls.outro = Usuario.objects.create_user("joao", password="x", perfil=P.CLIENTE)
        cls.prof = Profissional.objects.create(usuario=cls.u_prof, especialidade="Cabelo")
        cls.prof.servicos.add(cls.corte)

    def agendar(self, quando, servico=None, status=S.PENDENTE, cliente=None):
        return Agendamento.objects.create(
            cliente=cliente or self.cliente, profissional=self.prof,
            servico=servico or self.corte, data_hora=quando, status=status,
        )

    def horario(self, quando, minutos=60, prof=None):
        return HorarioDisponivel.objects.create(
            profissional=prof or self.prof, inicio=quando, fim=quando + timedelta(minutes=minutos)
        )

    def reservar(self, horario, servico=None, status=S.PENDENTE, cliente=None):
        return Agendamento.objects.create(
            cliente=cliente or self.cliente, profissional=horario.profissional,
            servico=servico or self.corte, horario=horario, status=status,
        )


class RegrasDeNegocioTests(BaseTest):
    def novo(self, quando, servico=None):
        return Agendamento(cliente=self.cliente, profissional=self.prof,
                           servico=servico or self.corte, data_hora=quando)

    def test_horario_valido_passa(self):
        self.novo(proximo_horario()).full_clean()

    def test_nao_agenda_no_passado(self):
        with self.assertRaises(ValidationError) as ctx:
            self.novo(timezone.now() - timedelta(hours=1)).full_clean()
        self.assertIn("data_hora", ctx.exception.message_dict)

    def test_profissional_precisa_realizar_o_servico(self):
        with self.assertRaises(ValidationError) as ctx:
            self.novo(proximo_horario(), servico=self.barba).full_clean()
        self.assertIn("servico", ctx.exception.message_dict)

    def test_conflito_de_horario(self):
        self.agendar(proximo_horario(10))
        with self.assertRaises(ValidationError):
            self.novo(proximo_horario(10)).full_clean()

    def test_sobreposicao_considera_a_duracao(self):
        self.agendar(proximo_horario(10))  # corte: 10:00–11:00
        with self.assertRaises(ValidationError):
            self.novo(proximo_horario(10) + timedelta(minutes=30)).full_clean()
        self.novo(proximo_horario(11)).full_clean()  # 11:00 já está livre

    def test_horario_cancelado_libera_a_vaga(self):
        self.agendar(proximo_horario(10), status=S.CANCELADO)
        self.novo(proximo_horario(10)).full_clean()

    def test_fora_do_expediente(self):
        with self.assertRaises(ValidationError):
            self.novo(proximo_horario(6)).full_clean()
        with self.assertRaises(ValidationError):
            self.novo(proximo_horario(18, dias=3) + timedelta(minutes=30)).full_clean()

    def test_domingo_fechado(self):
        d = proximo_horario()
        while d.weekday() != 6:
            d += timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.novo(d).full_clean()

    def test_preco_cobrado_fica_gravado(self):
        ag = self.agendar(proximo_horario())
        self.corte.preco = Decimal("99")
        self.corte.save()
        ag.refresh_from_db()
        self.assertEqual(ag.preco_cobrado, Decimal("50"))


class AcessoETelasTests(BaseTest):
    def test_anonimo_vai_para_login(self):
        r = self.client.get(reverse("cliente_agendamentos"))
        self.assertRedirects(r, f"{reverse('login')}?next={reverse('cliente_agendamentos')}")

    def test_perfil_errado_recebe_403(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("prof_agenda")).status_code, 403)
        self.assertEqual(self.client.get(reverse("gestao_painel")).status_code, 403)
        self.client.force_login(self.u_prof)
        self.assertEqual(self.client.get(reverse("cliente_agendamentos")).status_code, 403)

    def test_cada_perfil_e_levado_para_sua_area(self):
        for user, destino in [(self.cliente, "cliente_agendamentos"),
                              (self.u_prof, "prof_agenda"), (self.admin, "gestao_painel")]:
            self.client.force_login(user)
            self.assertRedirects(self.client.get(reverse("dashboard")), reverse(destino),
                                 fetch_redirect_response=False)

    def test_cadastro_cria_cliente(self):
        r = self.client.post(reverse("cadastro"), {
            "first_name": "Carla", "last_name": "Dias", "username": "carla", "email": "c@x.com",
            "telefone": "35999990000", "password1": "Senha-Forte-123", "password2": "Senha-Forte-123",
        })
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)
        u = Usuario.objects.get(username="carla")
        self.assertEqual(u.perfil, P.CLIENTE)
        self.assertFalse(u.is_staff)

    def test_cadastro_nao_deixa_escolher_perfil(self):
        self.client.post(reverse("cadastro"), {
            "first_name": "Hack", "last_name": "Er", "username": "hacker", "email": "h@x.com",
            "password1": "Senha-Forte-123", "password2": "Senha-Forte-123", "perfil": "ADMIN",
        })
        self.assertEqual(Usuario.objects.get(username="hacker").perfil, P.CLIENTE)

    def test_login_e_logout(self):
        self.assertTrue(self.client.login(username="maria", password="x"))
        r = self.client.post(reverse("logout"))
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("cliente_agendamentos")).status_code, 302)

    def test_cliente_cria_agendamento(self):
        self.client.force_login(self.cliente)
        h = self.horario(proximo_horario())
        r = self.client.post(reverse("agendamento_novo"), {
            "profissional": self.prof.pk, "servico": self.corte.pk,
            "horario": h.pk, "observacoes": "",
        })
        self.assertRedirects(r, reverse("cliente_agendamentos"), fetch_redirect_response=False)
        ag = Agendamento.objects.get()
        self.assertEqual((ag.cliente, ag.status, ag.horario), (self.cliente, S.PENDENTE, h))
        self.assertEqual(ag.data_hora, h.inicio)

    def test_formulario_rejeita_horario_ja_reservado(self):
        h = self.horario(proximo_horario(10))
        self.reservar(h, cliente=self.outro)
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("agendamento_novo"), {
            "profissional": self.prof.pk, "servico": self.corte.pk, "horario": h.pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "não está mais disponível")
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_formulario_exige_horario_cadastrado(self):
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("agendamento_novo"), {
            "profissional": self.prof.pk, "servico": self.corte.pk,
            "data_hora": proximo_horario().strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Escolha um horário disponível")
        self.assertFalse(Agendamento.objects.exists())

    def test_formulario_traduzido_e_sem_select_em_ingles(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("agendamento_novo"), {"profissional": self.prof.pk})
        self.assertContains(r, "Com quem você quer agendar?")
        self.assertNotContains(r, "Select an option")

    def test_cliente_cancela_o_proprio(self):
        ag = self.agendar(proximo_horario())
        self.client.force_login(self.cliente)
        self.client.post(reverse("agendamento_cancelar", args=[ag.pk]))
        ag.refresh_from_db()
        self.assertEqual(ag.status, S.CANCELADO)

    def test_cliente_nao_cancela_de_outro(self):
        ag = self.agendar(proximo_horario(), cliente=self.outro)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(reverse("agendamento_cancelar", args=[ag.pk])).status_code, 404)

    def test_lista_do_cliente_mostra_so_os_dele(self):
        self.agendar(proximo_horario(10), cliente=self.cliente)
        self.agendar(proximo_horario(14), cliente=self.outro)
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("cliente_agendamentos"))
        self.assertEqual(len(r.context["agendamentos"]), 1)

    def test_profissional_confirma_e_conclui(self):
        ag = self.agendar(proximo_horario())
        self.client.force_login(self.u_prof)
        url = reverse("prof_acao", args=[ag.pk])
        self.client.post(url, {"acao": "concluir"})  
        ag.refresh_from_db()
        self.assertEqual(ag.status, S.PENDENTE)
        self.client.post(url, {"acao": "confirmar"})
        self.client.post(url, {"acao": "concluir"})
        ag.refresh_from_db()
        self.assertEqual(ag.status, S.CONCLUIDO)

    def test_agenda_do_profissional(self):
        ag = self.agendar(proximo_horario())
        self.client.force_login(self.u_prof)
        dia = timezone.localtime(ag.data_hora).date().isoformat()
        r = self.client.get(reverse("prof_agenda"), {"data": dia})
        self.assertContains(r, "Corte")

    def test_painel_de_gestao_soma_faturamento(self):
        self.agendar(timezone.now() - timedelta(hours=1), status=S.CONCLUIDO)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("gestao_painel"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["faturamento"], Decimal("50"))
        self.assertEqual(r.context["ticket_medio"], Decimal("50"))
        self.assertEqual(sum(r.context["grafico"]["status"]["valores"]), 1)

    def test_api_servicos_do_profissional(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("api_servicos", args=[self.prof.pk]))
        self.assertEqual([s["nome"] for s in r.json()], ["Corte"])

    def test_admin_django_exige_staff(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/salao/agendamento/?periodo=semana&status=PEND").status_code, 200)

    def test_pagina_inicial_publica(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)


class HorariosEAgendamentoTests(BaseTest):
    def test_horario_define_data_hora_e_passa_na_validacao(self):
        h = self.horario(proximo_horario())
        ag = Agendamento(cliente=self.cliente, profissional=self.prof, servico=self.corte, horario=h)
        ag.full_clean()
        self.assertEqual(ag.data_hora, h.inicio)

    def test_sem_horario_nem_data_e_erro(self):
        ag = Agendamento(cliente=self.cliente, profissional=self.prof, servico=self.corte)
        with self.assertRaises(ValidationError) as ctx:
            ag.full_clean()
        self.assertIn("horario", ctx.exception.message_dict)

    def test_servico_precisa_caber_no_horario(self):
        self.prof.servicos.add(self.barba)
        curto = self.horario(proximo_horario(10), minutos=30)
        ag = Agendamento(cliente=self.cliente, profissional=self.prof, servico=self.corte, horario=curto)
        with self.assertRaises(ValidationError) as ctx:
            ag.full_clean()
        self.assertIn("servico", ctx.exception.message_dict)
        Agendamento(cliente=self.cliente, profissional=self.prof, servico=self.barba, horario=curto).full_clean()

    def test_horario_de_outro_profissional_e_recusado(self):
        u2 = Usuario.objects.create_user("bia", password="x", perfil=P.PROFISSIONAL)
        outra = Profissional.objects.create(usuario=u2, especialidade="Unhas")
        h = self.horario(proximo_horario(), prof=outra)
        ag = Agendamento(cliente=self.cliente, profissional=self.prof, servico=self.corte, horario=h)
        with self.assertRaises(ValidationError) as ctx:
            ag.full_clean()
        self.assertIn("horario", ctx.exception.message_dict)

    def test_horario_reservado_nao_reserva_de_novo(self):
        h = self.horario(proximo_horario())
        self.reservar(h)
        ag = Agendamento(cliente=self.outro, profissional=self.prof, servico=self.corte, horario=h)
        with self.assertRaises(ValidationError):
            ag.full_clean()

    def test_cancelar_libera_o_horario(self):
        h = self.horario(proximo_horario())
        ag = self.reservar(h)
        self.assertFalse(HorarioDisponivel.objects.livres().filter(pk=h.pk).exists())
        ag.status = S.CANCELADO
        ag.save()
        self.assertTrue(HorarioDisponivel.objects.livres().filter(pk=h.pk).exists())
        self.reservar(h, cliente=self.outro)  # a vaga pode ser reservada de novo

    def test_banco_impede_duas_reservas_ativas_do_mesmo_horario(self):
        from django.db import IntegrityError, transaction
        h = self.horario(proximo_horario())
        self.reservar(h)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.reservar(h, cliente=self.outro)

    def test_horario_nao_pode_ser_domingo_nem_fora_do_expediente_nem_sobrepor(self):
        d = proximo_horario()
        while d.weekday() != 6:
            d += timedelta(days=1)
        with self.assertRaises(ValidationError):
            HorarioDisponivel(profissional=self.prof, inicio=d, fim=d + timedelta(hours=1)).full_clean()
        with self.assertRaises(ValidationError):
            HorarioDisponivel(profissional=self.prof, inicio=proximo_horario(6),
                              fim=proximo_horario(7)).full_clean()
        self.horario(proximo_horario(10))
        with self.assertRaises(ValidationError):
            HorarioDisponivel(profissional=self.prof, inicio=proximo_horario(10) + timedelta(minutes=30),
                              fim=proximo_horario(12)).full_clean()

    def test_api_lista_so_horarios_livres_que_comportam_o_servico(self):
        longo = self.horario(proximo_horario(10), minutos=60)
        self.horario(proximo_horario(14), minutos=30)          # curto demais para o corte (60 min)
        ocupado = self.horario(proximo_horario(16), minutos=60)
        self.reservar(ocupado)
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("api_horarios", args=[self.prof.pk]), {"servico": self.corte.pk})
        ids = [h["id"] for dia in r.json()["dias"] for h in dia["horarios"]]
        self.assertEqual(ids, [longo.pk])

    def test_api_horarios_so_para_cliente(self):
        self.client.force_login(self.u_prof)
        self.assertEqual(self.client.get(reverse("api_horarios", args=[self.prof.pk])).status_code, 403)


class ProfissionalAreaTests(BaseTest):
    def dia_util(self, dias=3):
        return proximo_horario(9, dias=dias).date()

    def test_gera_horarios_em_blocos(self):
        self.client.force_login(self.u_prof)
        r = self.client.post(reverse("prof_horarios"), {
            "data": self.dia_util().isoformat(), "repetir_ate": "",
            "hora_inicio": "09:00", "hora_fim": "12:00", "duracao": "60",
        })
        self.assertRedirects(r, reverse("prof_horarios"), fetch_redirect_response=False)
        horas = [timezone.localtime(h.inicio).strftime("%H:%M") for h in self.prof.horarios.all()]
        self.assertEqual(horas, ["09:00", "10:00", "11:00"])

    def test_repetir_pula_domingo_e_nao_duplica(self):
        d = proximo_horario(9, dias=3).date()
        while d.weekday() != 5:      # próximo sábado
            d += timedelta(days=1)
        dados = {"data": d.isoformat(), "repetir_ate": (d + timedelta(days=2)).isoformat(),
                 "hora_inicio": "09:00", "hora_fim": "10:00", "duracao": "60"}
        self.client.force_login(self.u_prof)
        self.client.post(reverse("prof_horarios"), dados)
        self.assertEqual(self.prof.horarios.count(), 2)          # sábado e segunda
        self.client.post(reverse("prof_horarios"), dados)
        self.assertEqual(self.prof.horarios.count(), 2)          # repetir não duplica

    def test_formulario_de_horarios_valida(self):
        self.client.force_login(self.u_prof)
        r = self.client.post(reverse("prof_horarios"), {
            "data": self.dia_util().isoformat(), "hora_inicio": "12:00", "hora_fim": "10:00", "duracao": "60"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.prof.horarios.count(), 0)

    def test_exclui_horario_livre_mas_nao_o_reservado(self):
        livre, ocupado = self.horario(proximo_horario(10)), self.horario(proximo_horario(14))
        self.reservar(ocupado)
        self.client.force_login(self.u_prof)
        self.client.post(reverse("prof_horario_excluir", args=[livre.pk]))
        self.client.post(reverse("prof_horario_excluir", args=[ocupado.pk]))
        self.assertFalse(HorarioDisponivel.objects.filter(pk=livre.pk).exists())
        self.assertTrue(HorarioDisponivel.objects.filter(pk=ocupado.pk).exists())

    def test_nao_exclui_horario_de_outro_profissional(self):
        u2 = Usuario.objects.create_user("bia", password="x", perfil=P.PROFISSIONAL)
        outra = Profissional.objects.create(usuario=u2, especialidade="Unhas")
        h = self.horario(proximo_horario(), prof=outra)
        self.client.force_login(self.u_prof)
        self.assertEqual(self.client.post(reverse("prof_horario_excluir", args=[h.pk])).status_code, 404)

    def test_telas_do_profissional_so_para_profissional(self):
        self.client.force_login(self.cliente)
        for nome in ("prof_horarios", "prof_perfil"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 403)

    def test_edita_o_proprio_perfil(self):
        self.client.force_login(self.u_prof)
        r = self.client.post(reverse("prof_perfil"), {
            "especialidade": "Colorista", "anos_experiencia": 7, "descricao": "Sou a Ana."})
        self.assertRedirects(r, reverse("prof_perfil"), fetch_redirect_response=False)
        self.prof.refresh_from_db()
        self.assertEqual((self.prof.especialidade, self.prof.anos_experiencia), ("Colorista", 7))
        self.assertEqual(self.client.get(reverse("prof_agenda")).status_code, 200)


class AvaliacaoETelasPublicasTests(BaseTest):
    def concluido(self, cliente=None):
        return self.agendar(timezone.now() - timedelta(days=1), status=S.CONCLUIDO, cliente=cliente)

    def test_cliente_avalia_atendimento_concluido(self):
        ag = self.concluido()
        self.client.force_login(self.cliente)
        url = reverse("agendamento_avaliar", args=[ag.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"nota": 5, "comentario": "Perfeito!"})
        self.assertRedirects(r, reverse("cliente_agendamentos"), fetch_redirect_response=False)
        av = Avaliacao.objects.get()
        self.assertEqual((av.agendamento, av.nota, av.profissional), (ag, 5, self.prof))

    def test_so_avalia_uma_vez(self):
        ag = self.concluido()
        self.client.force_login(self.cliente)
        url = reverse("agendamento_avaliar", args=[ag.pk])
        self.client.post(url, {"nota": 4})
        self.client.post(url, {"nota": 1})
        self.assertEqual(Avaliacao.objects.count(), 1)
        self.assertEqual(Avaliacao.objects.get().nota, 4)

    def test_nao_avalia_atendimento_nao_concluido(self):
        ag = self.agendar(proximo_horario(), status=S.CONFIRMADO)
        self.client.force_login(self.cliente)
        self.client.post(reverse("agendamento_avaliar", args=[ag.pk]), {"nota": 5})
        self.assertFalse(Avaliacao.objects.exists())

    def test_nao_avalia_atendimento_de_outro_cliente(self):
        ag = self.concluido(cliente=self.outro)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(reverse("agendamento_avaliar", args=[ag.pk]), {"nota": 5}).status_code, 404)

    def test_nota_obrigatoria_e_entre_1_e_5(self):
        ag = self.concluido()
        self.client.force_login(self.cliente)
        url = reverse("agendamento_avaliar", args=[ag.pk])
        self.assertContains(self.client.post(url, {"comentario": "x"}), "Escolha uma nota")
        self.client.post(url, {"nota": 9})
        self.assertFalse(Avaliacao.objects.exists())

    def test_lista_do_cliente_oferece_avaliar(self):
        self.concluido()
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("cliente_agendamentos"))
        self.assertContains(r, "Avaliar")
        self.assertEqual(r.context["para_avaliar"], 1)

    def test_media_do_profissional(self):
        for nota, cli in ((5, self.cliente), (4, self.outro)):
            Avaliacao.objects.create(agendamento=self.concluido(cliente=cli), nota=nota)
        self.assertEqual(self.prof.resumo_avaliacoes(), (4.5, 2))
        self.assertEqual(self.prof.nota_media, 4.5)

    def test_perfil_publico_mostra_descricao_e_avaliacoes(self):
        self.prof.descricao = "Cabeleireira apaixonada por cor."
        self.prof.save()
        Avaliacao.objects.create(agendamento=self.concluido(), nota=5, comentario="Amei o resultado")
        r = self.client.get(reverse("profissional_detalhe", args=[self.prof.pk]))
        self.assertContains(r, "Cabeleireira apaixonada por cor.")
        self.assertContains(r, "Amei o resultado")
        self.assertEqual(r.context["total_aval"], 1)

    def test_perfil_de_inativo_da_404(self):
        self.prof.ativo = False
        self.prof.save()
        self.assertEqual(self.client.get(reverse("profissional_detalhe", args=[self.prof.pk])).status_code, 404)

    def test_home_mostra_nota_dos_profissionais(self):
        Avaliacao.objects.create(agendamento=self.concluido(), nota=4)
        r = self.client.get(reverse("home"))
        self.assertContains(r, reverse("profissional_detalhe", args=[self.prof.pk]))


class PainelEAdminTests(BaseTest):
    def test_painel_calcula_indicadores_e_graficos(self):
        a1 = self.agendar(timezone.now() - timedelta(hours=3), status=S.CONCLUIDO)
        self.agendar(timezone.now() - timedelta(hours=2), servico=self.corte, status=S.CANCELADO, cliente=self.outro)
        Avaliacao.objects.create(agendamento=a1, nota=5)
        self.client.force_login(self.admin)
        r = self.client.get(reverse("gestao_painel"))
        self.assertEqual(r.status_code, 200)
        c = r.context
        self.assertEqual((c["total"], c["n_concluidos"], c["n_cancelados"]), (2, 1, 1))
        self.assertEqual(c["taxa_cancelamento"], 50)
        self.assertEqual(c["nota_media"], 5)
        self.assertEqual(len(c["grafico"]["dias"]), len(c["grafico"]["concluido"]))
        self.assertEqual(c["ranking"][0]["media"], 5)
        self.assertContains(r, "dados-grafico")

    def test_atalhos_de_periodo(self):
        self.client.force_login(self.admin)
        hoje = timezone.localdate()
        r = self.client.get(reverse("gestao_painel"), {
            "inicio": (hoje - timedelta(days=6)).isoformat(), "fim": hoje.isoformat()})
        self.assertTrue(r.context["atalhos"][0]["ativo"])

    def test_admin_django_novas_telas_e_filtros(self):
        self.client.force_login(self.admin)
        h = self.horario(proximo_horario())
        self.reservar(h)
        for url in ("/admin/salao/horariodisponivel/", "/admin/salao/horariodisponivel/?situacao=livre",
                    "/admin/salao/horariodisponivel/?situacao=reservado", "/admin/salao/avaliacao/",
                    "/admin/salao/avaliacao/?nota__exact=5", "/admin/salao/profissional/",
                    "/admin/salao/agendamento/add/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
