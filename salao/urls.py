from django.urls import path

from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    # cliente
    path("cliente/agendamentos/", views.ClienteAgendamentosView.as_view(), name="cliente_agendamentos"),
    path("cliente/agendamentos/novo/", views.AgendamentoCreateView.as_view(), name="agendamento_novo"),
    path("cliente/agendamentos/<int:pk>/cancelar/", views.AgendamentoCancelarView.as_view(), name="agendamento_cancelar"),
    path("api/profissionais/<int:pk>/servicos/", views.ServicosDoProfissionalAPI.as_view(), name="api_servicos"),
    # profissional
    path("profissional/agenda/", views.AgendaProfissionalView.as_view(), name="prof_agenda"),
    path("profissional/agendamentos/<int:pk>/acao/", views.AgendamentoAcaoView.as_view(), name="prof_acao"),
    # administrador
    path("gestao/", views.GestaoPainelView.as_view(), name="gestao_painel"),
]
