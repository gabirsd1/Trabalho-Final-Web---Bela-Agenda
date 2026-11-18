from datetime import date, datetime, time, timedelta

from django import forms
from django.utils import timezone

from accounts.forms import BootstrapFormMixin

from .models import (
    ABERTURA,
    DIA_FECHADO,
    FECHAMENTO,
    Agendamento,
    Avaliacao,
    HorarioDisponivel,
    Profissional,
    Servico,
)


class AgendamentoForm(BootstrapFormMixin, forms.ModelForm):
    """Formulário do cliente: escolhe profissional, serviço e um horário já cadastrado."""

    class Meta:
        model = Agendamento
        fields = ("profissional", "servico", "horario", "data_hora", "observacoes")
        widgets = {
            "profissional": forms.HiddenInput,
            "servico": forms.HiddenInput,
            "horario": forms.HiddenInput,
            "data_hora": forms.HiddenInput,
            "observacoes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Algum detalhe para o profissional? (opcional)"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profissional"].queryset = Profissional.objects.filter(ativo=True).select_related("usuario")
        self.fields["servico"].queryset = Servico.objects.filter(ativo=True)
        self.fields["horario"].queryset = HorarioDisponivel.objects.futuros().livres()
        self.fields["horario"].required = True
        self.fields["data_hora"].required = False
        msgs = {
            "profissional": ("Escolha um profissional.", "Profissional inválido."),
            "servico": ("Escolha um serviço.", "Serviço inválido."),
            "horario": ("Escolha um horário disponível.", "Esse horário não está mais disponível. Escolha outro."),
        }
        for nome, (obrigatorio, invalido) in msgs.items():
            self.fields[nome].error_messages.update(required=obrigatorio, invalid_choice=invalido)


class AvaliacaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Avaliacao
        fields = ("nota", "comentario")
        widgets = {
            "nota": forms.RadioSelect,
            "comentario": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Conte como foi o atendimento (opcional)"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nota"].choices = Avaliacao.NOTAS
        self.fields["nota"].error_messages["required"] = "Escolha uma nota de 1 a 5 estrelas."
        # o RadioSelect não usa a classe form-control
        self.fields["nota"].widget.attrs["class"] = "star-input"


class PerfilProfissionalForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profissional
        fields = ("especialidade", "anos_experiencia", "descricao", "foto")
        widgets = {
            "descricao": forms.Textarea(
                attrs={"rows": 5, "placeholder": "Conte sua trajetória, o que você mais gosta de fazer..."}
            ),
            "foto": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }


class GerarHorariosForm(BootstrapFormMixin, forms.Form):
    """O profissional informa um período e o sistema cria os horários em blocos."""

    DURACOES = [(30, "30 minutos"), (45, "45 minutos"), (60, "1 hora"), (90, "1h30"), (120, "2 horas")]

    data = forms.DateField(
        label="Dia", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    repetir_ate = forms.DateField(
        label="Repetir até (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Cria os mesmos horários em todos os dias até essa data (domingos são pulados).",
    )
    hora_inicio = forms.TimeField(
        label="Das", initial=time(9, 0), widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    )
    hora_fim = forms.TimeField(
        label="Até", initial=time(12, 0), widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    )
    duracao = forms.TypedChoiceField(
        label="Duração de cada horário", choices=DURACOES, coerce=int, initial=60
    )

    def clean(self):
        dados = super().clean()
        dia, ate = dados.get("data"), dados.get("repetir_ate")
        ini, fim = dados.get("hora_inicio"), dados.get("hora_fim")
        hoje = timezone.localdate()

        if dia and dia < hoje:
            self.add_error("data", "Escolha hoje ou uma data futura.")
        if dia and not ate and dia.weekday() == DIA_FECHADO:
            self.add_error("data", "O salão não abre aos domingos.")
        if dia and ate:
            if ate < dia:
                self.add_error("repetir_ate", "A data final precisa ser depois do primeiro dia.")
            elif (ate - dia).days > 60:
                self.add_error("repetir_ate", "Cadastre no máximo 60 dias por vez.")
        if ini and fim:
            if fim <= ini:
                self.add_error("hora_fim", "O horário final precisa ser depois do inicial.")
            elif ini < ABERTURA or fim > FECHAMENTO:
                self.add_error("hora_inicio", "O salão funciona das 08:00 às 19:00.")
            elif self.cleaned_data.get("duracao"):
                bloco = timedelta(minutes=self.cleaned_data["duracao"])
                if datetime.combine(date.min, ini) + bloco > datetime.combine(date.min, fim):
                    self.add_error("duracao", "O período é menor que a duração escolhida.")
        return dados

    def blocos(self):
        """Gera (inicio, fim) já com fuso horário, pulando domingos e horas que já passaram."""
        d = self.cleaned_data
        tz = timezone.get_current_timezone()
        bloco = timedelta(minutes=d["duracao"])
        agora = timezone.now()
        dia, ultimo = d["data"], d.get("repetir_ate") or d["data"]
        while dia <= ultimo:
            if dia.weekday() != DIA_FECHADO:
                cursor = datetime.combine(dia, d["hora_inicio"])
                limite = datetime.combine(dia, d["hora_fim"])
                while cursor + bloco <= limite:
                    inicio = timezone.make_aware(cursor, tz)
                    if inicio > agora:
                        yield inicio, inicio + bloco
                    cursor += bloco
            dia += timedelta(days=1)
