from django.urls import path

from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),

    path("cliente/agendamentos/", views.ClienteAgendamentosView.as_view(), name="cliente_agendamentos"),
    path("cliente/agendamentos/novo/", views.AgendamentoCreateView.as_view(), name="agendamento_novo"),
    path("cliente/agendamentos/<int:pk>/cancelar/", views.AgendamentoCancelarView.as_view(), name="agendamento_cancelar"),

    path("profissional/agenda/", views.AgendaProfissionalView.as_view(), name="prof_agenda"),
    path("profissional/agendamentos/<int:pk>/acao/", views.AgendamentoAcaoView.as_view(), name="prof_acao"),
    path("gestao/", views.GestaoPainelView.as_view(), name="gestao_painel"),
]
