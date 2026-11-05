from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import Agendamento, Categoria, Profissional, Servico


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
    list_display = ("usuario", "especialidade", "ativo")
    list_filter = ("ativo", "servicos__categoria")
    search_fields = ("usuario__username", "usuario__first_name", "especialidade")
    filter_horizontal = ("servicos",)
    autocomplete_fields = ("usuario",)


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "profissional", "servico", "data_hora", "status", "preco_cobrado")
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
