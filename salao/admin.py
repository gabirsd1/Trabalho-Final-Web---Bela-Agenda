from datetime import timedelta

from django.contrib import admin
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import Agendamento, Avaliacao, Categoria, HorarioDisponivel, Profissional, Servico


class PeriodoFilter(admin.SimpleListFilter):
    """Filtro personalizado: atalhos de período para os agendamentos."""

    title = "período"
    parameter_name = "periodo"

    def lookups(self, request, model_admin):
        return [
            ("hoje", "Hoje"),
            ("semana", "Próximos 7 dias"),
            ("passados", "Já realizados (passado)"),
        ]

    def queryset(self, request, queryset):
        agora = timezone.now()
        hoje = timezone.localdate()
        if self.value() == "hoje":
            return queryset.filter(data_hora__date=hoje)
        if self.value() == "semana":
            return queryset.filter(data_hora__gte=agora, data_hora__lt=agora + timedelta(days=7))
        if self.value() == "passados":
            return queryset.filter(data_hora__lt=agora)
        return queryset


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome",)
    search_fields = ("nome",)


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "preco", "duracao_min", "ativo")
    list_filter = ("categoria", "ativo")
    list_editable = ("ativo",)
    search_fields = ("nome", "descricao")


@admin.register(Profissional)
class ProfissionalAdmin(admin.ModelAdmin):
    list_display = ("usuario", "especialidade", "anos_experiencia", "nota", "ativo")
    list_filter = ("ativo", "servicos__categoria")
    search_fields = ("usuario__username", "usuario__first_name", "especialidade")
    filter_horizontal = ("servicos",)
    autocomplete_fields = ("usuario",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_media=Avg("agendamentos__avaliacao__nota"))

    @admin.display(description="nota média", ordering="_media")
    def nota(self, obj):
        return f"{obj._media:.1f} ★".replace(".", ",") if obj._media is not None else "—"


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "profissional", "servico", "data_hora", "status", "preco_cobrado")
    autocomplete_fields = ("cliente",)
    raw_id_fields = ("horario",)
    list_filter = (
        "status",
        PeriodoFilter,
        "profissional",
        "servico__categoria",
        ("data_hora", admin.DateFieldListFilter),
    )
    search_fields = ("cliente__username", "cliente__first_name", "cliente__last_name", "servico__nome")
    date_hierarchy = "data_hora"
    list_editable = ("status",)
    readonly_fields = ("preco_cobrado", "criado_em")
    list_select_related = ("cliente", "profissional__usuario", "servico")


class SituacaoHorarioFilter(admin.SimpleListFilter):
    """Filtro personalizado: horários livres x reservados."""

    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [("livre", "Livres"), ("reservado", "Reservados")]

    def queryset(self, request, queryset):
        if self.value() == "livre":
            return queryset.filter(_reservas=0)
        if self.value() == "reservado":
            return queryset.filter(_reservas__gt=0)
        return queryset


@admin.register(HorarioDisponivel)
class HorarioDisponivelAdmin(admin.ModelAdmin):
    list_display = ("profissional", "inicio", "fim", "duracao", "situacao")
    list_filter = (
        "profissional",
        SituacaoHorarioFilter,
        ("inicio", admin.DateFieldListFilter),
    )
    search_fields = ("profissional__usuario__first_name", "profissional__usuario__username")
    date_hierarchy = "inicio"
    list_select_related = ("profissional__usuario",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _reservas=Count("agendamentos", filter=~Q(agendamentos__status="CANC"))
        )

    @admin.display(description="duração (min)")
    def duracao(self, obj):
        return obj.duracao_min

    @admin.display(description="situação", ordering="_reservas")
    def situacao(self, obj):
        return "Reservado" if obj._reservas else "Livre"


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    list_display = ("profissional_", "cliente_", "servico_", "nota", "criado_em")
    list_filter = ("nota", "agendamento__profissional", ("criado_em", admin.DateFieldListFilter))
    search_fields = ("comentario", "agendamento__cliente__username", "agendamento__cliente__first_name")
    readonly_fields = ("criado_em",)
    list_select_related = ("agendamento__profissional__usuario", "agendamento__cliente", "agendamento__servico")
    raw_id_fields = ("agendamento",)

    @admin.display(description="profissional")
    def profissional_(self, obj):
        return obj.agendamento.profissional

    @admin.display(description="cliente")
    def cliente_(self, obj):
        return obj.agendamento.cliente

    @admin.display(description="serviço")
    def servico_(self, obj):
        return obj.agendamento.servico
