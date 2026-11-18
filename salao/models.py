from datetime import time, timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
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
    descricao = models.TextField(
        "sobre", blank=True, help_text="Texto de apresentação exibido no perfil público."
    )
    anos_experiencia = models.PositiveSmallIntegerField("anos de experiência", default=0)
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

    def resumo_avaliacoes(self):
        """Média (ou None) e quantidade de avaliações recebidas."""
        r = Avaliacao.objects.filter(agendamento__profissional=self).aggregate(
            media=Avg("nota"), total=Count("id")
        )
        return r["media"], r["total"]

    @property
    def nota_media(self):
        media, _ = self.resumo_avaliacoes()
        return round(media, 1) if media is not None else None

    def __str__(self):
        return str(self.usuario)


class HorarioQuerySet(models.QuerySet):
    def futuros(self):
        return self.filter(inicio__gt=timezone.now())

    def livres(self):
        """Horários sem nenhum agendamento ativo (cancelados liberam a vaga)."""
        return self.annotate(
            reservas=Count("agendamentos", filter=~Q(agendamentos__status="CANC"))
        ).filter(reservas=0)


class HorarioDisponivel(models.Model):
    """Janela de atendimento cadastrada pelo profissional; o cliente escolhe entre elas."""

    profissional = models.ForeignKey(
        Profissional, on_delete=models.CASCADE, related_name="horarios"
    )
    inicio = models.DateTimeField("início")
    fim = models.DateTimeField("fim")

    objects = HorarioQuerySet.as_manager()

    class Meta:
        verbose_name = "horário disponível"
        verbose_name_plural = "horários disponíveis"
        ordering = ["inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["profissional", "inicio"], name="horario_unico_por_profissional"
            ),
        ]

    @property
    def duracao_min(self):
        return int((self.fim - self.inicio).total_seconds() // 60)

    @property
    def reservado(self):
        return self.agendamentos.exclude(status="CANC").exists()

    def clean(self):
        if not (self.inicio and self.fim):
            return
        if self.fim <= self.inicio:
            raise ValidationError({"fim": "O fim precisa ser depois do início."})
        ini, fim = timezone.localtime(self.inicio), timezone.localtime(self.fim)
        if ini.weekday() == DIA_FECHADO:
            raise ValidationError({"inicio": "O salão não abre aos domingos."})
        if ini.time() < ABERTURA or fim.time() > FECHAMENTO or fim.date() != ini.date():
            raise ValidationError({"inicio": "O horário precisa ficar entre 08:00 e 19:00."})
        if self.profissional_id:
            sobrepoe = (
                HorarioDisponivel.objects.filter(
                    profissional_id=self.profissional_id, inicio__lt=self.fim, fim__gt=self.inicio
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if sobrepoe:
                raise ValidationError(
                    {"inicio": "Já existe outro horário deste profissional nesse intervalo."}
                )

    def __str__(self):
        ini, fim = timezone.localtime(self.inicio), timezone.localtime(self.fim)
        return f"{self.profissional} · {ini:%d/%m %H:%M}–{fim:%H:%M}"


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
    horario = models.ForeignKey(
        HorarioDisponivel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos",
        verbose_name="horário",
    )
    data_hora = models.DateTimeField(
        "data e hora", blank=True, help_text="Preenchida automaticamente a partir do horário escolhido."
    )
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
            models.UniqueConstraint(
                fields=["horario"],
                condition=~Q(status="CANC"),
                name="horario_com_um_agendamento_ativo",
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

    @property
    def pode_avaliar(self):
        return self.status == self.Status.CONCLUIDO and self.avaliacao_feita is None

    @property
    def avaliacao_feita(self):
        try:
            return self.avaliacao
        except ObjectDoesNotExist:
            return None

    def clean(self):
        erros = {}

        if self.horario_id:
            if not (self.profissional_id and self.servico_id):
                return
            h = self.horario
            if h.profissional_id != self.profissional_id:
                erros["horario"] = "Este horário pertence a outro profissional."
            else:
                self.data_hora = h.inicio
                if self.servico.duracao_min > h.duracao_min:
                    erros["servico"] = (
                        f"Este serviço leva {self.servico.duracao_min} min, mas o horário "
                        f"escolhido tem só {h.duracao_min} min."
                    )
                ocupado = (
                    Agendamento.objects.filter(horario=h)
                    .exclude(status=self.Status.CANCELADO)
                    .exclude(pk=self.pk)
                    .exists()
                )
                if ocupado and self.status != self.Status.CANCELADO:
                    erros["horario"] = "Esse horário acabou de ser reservado. Escolha outro."
        elif not self.data_hora:
            raise ValidationError({"horario": "Escolha um horário disponível."})

        if not (self.data_hora and self.profissional_id and self.servico_id):
            if erros:
                raise ValidationError(erros)
            return

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
        if self.horario_id:
            self.data_hora = self.horario.inicio
        if self.preco_cobrado is None and self.servico_id:
            self.preco_cobrado = self.servico.preco
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cliente} · {self.servico} · {timezone.localtime(self.data_hora):%d/%m %H:%M}"


class Avaliacao(models.Model):
    """Nota e comentário do cliente sobre um atendimento concluído."""

    NOTAS = [(1, "Péssimo"), (2, "Ruim"), (3, "Regular"), (4, "Bom"), (5, "Excelente")]

    agendamento = models.OneToOneField(
        Agendamento, on_delete=models.CASCADE, related_name="avaliacao"
    )
    nota = models.PositiveSmallIntegerField(
        choices=NOTAS, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField("comentário", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"
        ordering = ["-criado_em"]

    @property
    def profissional(self):
        return self.agendamento.profissional

    @property
    def cliente(self):
        return self.agendamento.cliente

    def clean(self):
        if self.agendamento_id and self.agendamento.status != Agendamento.Status.CONCLUIDO:
            raise ValidationError("Só é possível avaliar atendimentos concluídos.")

    def __str__(self):
        return f"{self.nota}/5 · {self.agendamento}"
