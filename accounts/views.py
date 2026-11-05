from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.generic import CreateView

from .forms import CadastroForm


class CadastroView(CreateView):
    form_class = CadastroForm
    template_name = "accounts/cadastro.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, f"Bem-vindo(a), {user.first_name}! Sua conta foi criada.")
        return redirect("dashboard")


@login_required
def dashboard(request):
    """Envia cada perfil para a sua área."""
    user = request.user
    if user.eh_admin:
        return redirect("gestao_painel")
    if user.eh_profissional:
        return redirect("prof_agenda")
    return redirect("cliente_agendamentos")
