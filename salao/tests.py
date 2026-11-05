from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario

from .models import Agendamento, Categoria, Profissional, Servico

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
        quando = proximo_horario()
        r = self.client.post(reverse("agendamento_novo"), {
            "profissional": self.prof.pk, "servico": self.corte.pk,
            "data_hora": quando.strftime("%Y-%m-%dT%H:%M"), "observacoes": "",
        })
        self.assertRedirects(r, reverse("cliente_agendamentos"), fetch_redirect_response=False)
        ag = Agendamento.objects.get()
        self.assertEqual((ag.cliente, ag.status), (self.cliente, S.PENDENTE))

    def test_formulario_rejeita_conflito(self):
        self.agendar(proximo_horario(10), cliente=self.outro)
        self.client.force_login(self.cliente)
        r = self.client.post(reverse("agendamento_novo"), {
            "profissional": self.prof.pk, "servico": self.corte.pk,
            "data_hora": proximo_horario(10).strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Horário indisponível")

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
