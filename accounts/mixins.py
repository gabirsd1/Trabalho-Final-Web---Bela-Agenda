from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class PerfilRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Exige login e que o perfil do usuário esteja em `perfis`.

    - Anônimo            -> redireciona para o login
    - Perfil não permitido -> erro 403 (acesso negado)
    """

    perfis = ()

    def test_func(self):
        return self.request.user.perfil in self.perfis
