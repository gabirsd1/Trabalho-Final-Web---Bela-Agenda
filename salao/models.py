from datetime import time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

ABERTURA = time(8, 0)
FECHAMENTO = time(19, 0)
DIA_FECHADO = 6  


class Categoria(models.Model):
    nome = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Servico(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="servicos")
    nome = models.CharField(max_length=100)
    descricao = models.TextField("descrição", blank=True)
    preco = models.DecimalField("preço", max_digits=8, decimal_places=2)
    duracao_min = models.PositiveIntegerField("duração (min)", default=30)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "serviço"
        verbose_name_plural = "serviços"
        ordering = ["categoria__nome", "nome"]

    def __str__(self):
        return self.nome


class Profissional(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profissional"
    )
    especialidade = models.CharField(max_length=100)
    servicos = models.ManyToManyField(Servico, related_name="profissionais", verbose_name="serviços")
    foto = models.ImageField(upload_to="profissionais/", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "profissional"
        verbose_name_plural = "profissionais"
        ordering = ["usuario__first_name", "usuario__username"]

    def clean(self):
      
        if self.usuario_id and self.usuario.perfil != self.usuario.Perfil.PROFISSIONAL:
            raise ValidationError(
                {"usuario": "Escolha um usuário com perfil 'Profissional'."}
            )

    def __str__(self):
        return str(self.usuario)


class Agendamento(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PEND", "Pendente"
        CONFIRMADO = "CONF", "Confirmado"
        CONCLUIDO = "CONC", "Concluído"
        CANCELADO = "CANC", "Cancelado"

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agendamentos"
    )
    profissional = models.ForeignKey(
        Profissional, on_delete=models.PROTECT, related_name="agendamentos"
    )
    servico = models.ForeignKey(Servico, on_delete=models.PROTECT, verbose_name="serviço")
    data_hora = models.DateTimeField("data e hora")
    status = models.CharField(max_length=4, choices=Status.choices, default=Status.PENDENTE)
    observacoes = models.TextField("observações", blank=True)
    preco_cobrado = models.DecimalField(
        "preço cobrado", max_digits=8, decimal_places=2, null=True, blank=True, editable=False
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data_hora"]
        constraints = [
     
            models.UniqueConstraint(
                fields=["profissional", "data_hora"],
                condition=~Q(status="CANC"),
                name="sem_conflito_de_horario",
            ),
        ]

 
    @property
    def fim(self):
        return self.data_hora + timedelta(minutes=self.servico.duracao_min)

    @property
    def badge_class(self):
        return {
            self.Status.PENDENTE: "text-bg-warning",
            self.Status.CONFIRMADO: "text-bg-primary",
            self.Status.CONCLUIDO: "text-bg-success",
            self.Status.CANCELADO: "text-bg-secondary",
        }[self.status]

    @property
    def pode_cancelar(self):
        return (
            self.status in (self.Status.PENDENTE, self.Status.CONFIRMADO)
            and self.data_hora > timezone.now()
        )

    def clean(self):
        if not (self.data_hora and self.profissional_id and self.servico_id):
            return

        erros = {}

        if self._state.adding and self.data_hora <= timezone.now():
            erros["data_hora"] = "Escolha uma data e hora no futuro."

        inicio_local = timezone.localtime(self.data_hora)
        fim_local = inicio_local + timedelta(minutes=self.servico.duracao_min)
        if inicio_local.weekday() == DIA_FECHADO:
            erros["data_hora"] = "O salão não abre aos domingos."
        elif inicio_local.time() < ABERTURA or fim_local.time() > FECHAMENTO or fim_local.date() != inicio_local.date():
            erros["data_hora"] = "O atendimento precisa ocorrer entre 08:00 e 19:00."

        if not self.profissional.servicos.filter(pk=self.servico_id).exists():
            erros["servico"] = "Este profissional não realiza o serviço escolhido."

        if "data_hora" not in erros:
     
            fim = self.data_hora + timedelta(minutes=self.servico.duracao_min)
            vizinhos = (
                Agendamento.objects.filter(
                    profissional=self.profissional,
                    data_hora__lt=fim,
                    data_hora__gte=self.data_hora - timedelta(hours=12),
                )
                .exclude(status=self.Status.CANCELADO)
                .exclude(pk=self.pk)
                .select_related("servico")
            )
            for outro in vizinhos:
                if outro.fim > self.data_hora:
                    erros["data_hora"] = (
                        f"Horário indisponível: {self.profissional} já tem atendimento "
                        f"das {timezone.localtime(outro.data_hora):%H:%M} às "
                        f"{timezone.localtime(outro.fim):%H:%M}."
                    )
                    break

        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):

        if self.preco_cobrado is None and self.servico_id:
            self.preco_cobrado = self.servico.preco
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente} · {self.servico} · {timezone.localtime(self.data_hora):%d/%m %H:%M}"
