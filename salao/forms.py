from django import forms

from accounts.forms import BootstrapFormMixin

from .models import Agendamento, Profissional, Servico


class AgendamentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ("profissional", "servico", "data_hora", "observacoes")
        widgets = {
            "data_hora": forms.DateTimeInput(
                attrs={"type": "datetime-local", "step": 900}, format="%Y-%m-%dT%H:%M"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profissional"].queryset = Profissional.objects.filter(ativo=True).select_related("usuario")
        self.fields["servico"].queryset = Servico.objects.filter(ativo=True)
        self.fields["data_hora"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
