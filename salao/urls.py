from django.urls import path

from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("profissionais/<int:pk>/", views.ProfissionalDetalheView.as_view(), name="profissional_detalhe"),

    path("cliente/agendamentos/", views.ClienteAgendamentosView.as_view(), name="cliente_agendamentos"),
    path("cliente/agendamentos/novo/", views.AgendamentoCreateView.as_view(), name="agendamento_novo"),
    path("cliente/agendamentos/<int:pk>/cancelar/", views.AgendamentoCancelarView.as_view(), name="agendamento_cancelar"),
    path("cliente/agendamentos/<int:pk>/avaliar/", views.AvaliarAgendamentoView.as_view(), name="agendamento_avaliar"),
    path("cliente/api/profissionais/<int:pk>/servicos/", views.ServicosDoProfissionalAPI.as_view(), name="api_servicos"),
    path("cliente/api/profissionais/<int:pk>/horarios/", views.HorariosDoProfissionalAPI.as_view(), name="api_horarios"),

    path("profissional/agenda/", views.AgendaProfissionalView.as_view(), name="prof_agenda"),
    path("profissional/agendamentos/<int:pk>/acao/", views.AgendamentoAcaoView.as_view(), name="prof_acao"),
    path("profissional/horarios/", views.ProfissionalHorariosView.as_view(), name="prof_horarios"),
    path("profissional/horarios/<int:pk>/excluir/", views.HorarioExcluirView.as_view(), name="prof_horario_excluir"),
    path("profissional/perfil/", views.ProfissionalPerfilView.as_view(), name="prof_perfil"),

    path("gestao/", views.GestaoPainelView.as_view(), name="gestao_painel"),
]
