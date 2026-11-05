from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuário do sistema com perfil (Administrador, Profissional ou Cliente)."""

    class Perfil(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        PROFISSIONAL = "PROF", "Profissional"
        CLIENTE = "CLI", "Cliente"

    perfil = models.CharField(max_length=5, choices=Perfil.choices, default=Perfil.CLIENTE)
    telefone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def save(self, *args, **kwargs):
       
        if self.is_superuser:
            self.perfil = self.Perfil.ADMIN
        if self.perfil == self.Perfil.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    @property
    def eh_admin(self):
        return self.perfil == self.Perfil.ADMIN

    @property
    def eh_profissional(self):
        return self.perfil == self.Perfil.PROFISSIONAL

    @property
    def eh_cliente(self):
        return self.perfil == self.Perfil.CLIENTE

    def __str__(self):
        return self.get_full_name() or self.username
