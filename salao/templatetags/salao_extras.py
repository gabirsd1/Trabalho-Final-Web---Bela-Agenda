from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def estrelas(nota, tamanho=""):
    """Desenha 5 estrelas (cheias, meias ou vazias) para uma nota de 0 a 5."""
    if nota is None:
        valor, rotulo = 0.0, "Ainda sem avaliações"
    else:
        valor = float(nota)
        rotulo = f"Nota {valor:.1f} de 5".replace(".", ",")
    icones = []
    for i in range(1, 6):
        if valor >= i - 0.25:
            icones.append("bi-star-fill")
        elif valor >= i - 0.75:
            icones.append("bi-star-half")
        else:
            icones.append("bi-star")
    miolo = format_html_join("", '<i class="bi {}"></i>', ((c,) for c in icones))
    vazio = " stars-empty" if nota is None else ""
    return format_html(
        '<span class="stars {}{}" role="img" aria-label="{}">{}</span>',
        tamanho, mark_safe(vazio), rotulo, miolo,
    )


@register.filter
def inicial(usuario):
    """Primeira letra do nome (ou do login) para o avatar."""
    nome = (usuario.first_name or usuario.username or "?").strip()
    return nome[:1].upper()
