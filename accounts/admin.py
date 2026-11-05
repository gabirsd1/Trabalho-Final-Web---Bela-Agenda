from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "email", "perfil", "is_active", "date_joined")
    list_filter = ("perfil", "is_active", "is_staff", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email", "telefone")
    fieldsets = UserAdmin.fieldsets + (("Salão", {"fields": ("perfil", "telefone")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Salão", {"fields": ("first_name", "last_name", "email", "perfil", "telefone")}),
    )
