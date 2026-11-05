from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Usuario


class BootstrapFormMixin:
    """Aplica as classes do Bootstrap em todos os campos do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()

    def full_clean(self):
        super().full_clean()
        if self._errors:
            for name in self._errors:
                if name in self.fields:
                    attrs = self.fields[name].widget.attrs
                    attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


class CadastroForm(BootstrapFormMixin, UserCreationForm):
    """Cadastro público: sempre cria um usuário com perfil Cliente."""

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("first_name", "last_name", "username", "email", "telefone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        self.fields["telefone"].widget.attrs["placeholder"] = "(35) 99999-9999"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.perfil = Usuario.Perfil.CLIENTE
        if commit:
            user.save()
        return user
