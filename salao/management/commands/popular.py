import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Usuario
from salao.models import Agendamento, Avaliacao, Categoria, HorarioDisponivel, Profissional, Servico

P = Usuario.Perfil
S = Agendamento.Status

DESCRICAO_ANA = (
    "Cabeleireira há 8 anos, apaixonada por transformar o visual com cuidado e naturalidade. "
    "Especialista em coloração, mechas e cortes femininos. Faz uma consulta rápida antes de "
    "começar para entender exatamente o que você quer."
)
DESCRICAO_BRUNO = (
    "Barbeiro e manicure com 5 anos de experiência. Trabalha com barba na régua, cortes "
    "masculinos clássicos e modernos e cuidado completo das unhas, sempre com atendimento pontual."
)
COMENTARIOS = {
    "ana": [
        "A Ana entendeu exatamente o que eu queria. Saí muito feliz com o cabelo!",
        "Coloração perfeita, atendimento atencioso e sem atraso.",
        "Super cuidadosa com o cabelo. Já marquei a próxima vez.",
        "Ótimo corte, só demorou um pouco mais que o previsto.",
    ],
    "bruno": [
        "Atendimento rápido e cheio de capricho. Vou voltar!",
        "Corte muito bem feito e ambiente agradável.",
        "O Bruno é pontual e caprichoso.",
        "Bom serviço, recomendo.",
    ],
}


class Command(BaseCommand):
    help = "Cria dados de exemplo (usuários, serviços, horários, agendamentos e avaliações)."

    def handle(self, *args, **opts):
        def usuario(username, senha, **extra):
            u, criado = Usuario.objects.get_or_create(username=username, defaults=extra)
            if criado:
                u.set_password(senha)
                u.save()
            return u

        usuario("admin", "admin123", first_name="Gerente", last_name="Bela",
                email="admin@belaagenda.com", perfil=P.ADMIN, is_superuser=True)
        ana = usuario("ana", "prof12345", first_name="Ana", last_name="Souza", perfil=P.PROFISSIONAL)
        bruno = usuario("bruno", "prof12345", first_name="Bruno", last_name="Lima", perfil=P.PROFISSIONAL)
        maria = usuario("maria", "cli12345", first_name="Maria", last_name="Alves",
                        email="maria@email.com", telefone="(35) 99999-0001", perfil=P.CLIENTE)
        joao = usuario("joao", "cli12345", first_name="João", last_name="Pereira",
                       email="joao@email.com", telefone="(35) 99999-0002", perfil=P.CLIENTE)

        cat = {n: Categoria.objects.get_or_create(nome=n)[0] for n in ("Cabelo", "Unhas", "Barba", "Estética")}
        catalogo = [
            ("Corte feminino", "Cabelo", "80.00", 60), ("Corte masculino", "Cabelo", "45.00", 30),
            ("Coloração", "Cabelo", "150.00", 120), ("Escova", "Cabelo", "60.00", 45),
            ("Manicure", "Unhas", "35.00", 45), ("Pedicure", "Unhas", "40.00", 45),
            ("Barba completa", "Barba", "30.00", 30), ("Limpeza de pele", "Estética", "120.00", 60),
        ]
        sv = {}
        for nome, c, preco, dur in catalogo:
            sv[nome], _ = Servico.objects.get_or_create(
                nome=nome, defaults={"categoria": cat[c], "preco": Decimal(preco), "duracao_min": dur})

        pa, _ = Profissional.objects.get_or_create(usuario=ana, defaults={"especialidade": "Cabelo e coloração"})
        pb, _ = Profissional.objects.get_or_create(usuario=bruno, defaults={"especialidade": "Barbeiro e unhas"})
        pa.servicos.set([sv["Corte feminino"], sv["Coloração"], sv["Escova"], sv["Corte masculino"]])
        pb.servicos.set([sv["Corte masculino"], sv["Barba completa"], sv["Manicure"], sv["Pedicure"]])

        # perfil: só preenche o que ainda está vazio, sem sobrescrever edições
        for prof, texto, anos in ((pa, DESCRICAO_ANA, 8), (pb, DESCRICAO_BRUNO, 5)):
            if not prof.descricao:
                prof.descricao = texto
            if not prof.anos_experiencia:
                prof.anos_experiencia = anos
            prof.save()

        base = timezone.localtime().replace(minute=0, second=0, microsecond=0)

        def dia(delta, hora):
            d = base + timedelta(days=delta)
            if d.weekday() == 6:  # pula domingo
                d += timedelta(days=1)
            return d.replace(hour=hora)

        def horario(prof, inicio, minutos=60):
            h, _ = HorarioDisponivel.objects.get_or_create(
                profissional=prof, inicio=inicio, defaults={"fim": inicio + timedelta(minutes=minutos)})
            return h

        if not Agendamento.objects.exists():
            dados = [
                (maria, pa, "Corte feminino", dia(-10, 9), S.CONCLUIDO),
                (joao, pb, "Barba completa", dia(-8, 10), S.CONCLUIDO),
                (maria, pa, "Coloração", dia(-3, 14), S.CONCLUIDO),
                (joao, pb, "Corte masculino", dia(-2, 11), S.CANCELADO),
                (maria, pa, "Escova", dia(1, 10), S.CONFIRMADO),
                (joao, pb, "Corte masculino", dia(1, 15), S.PENDENTE),
                (maria, pb, "Manicure", dia(2, 9), S.PENDENTE),
                (joao, pa, "Corte masculino", dia(3, 16), S.CONFIRMADO),
            ]
            for cli, prof, serv, quando, status in dados:
                futuro = quando > timezone.now() and status != S.CANCELADO
                Agendamento.objects.create(
                    cliente=cli, profissional=prof, servico=sv[serv], data_hora=quando, status=status,
                    horario=horario(prof, quando) if futuro else None)

        # histórico dos últimos 28 dias, para os gráficos do painel ficarem com o que mostrar
        if Agendamento.objects.count() < 15:
            sorteio = random.Random(7)
            clientes = [maria, joao]
            for delta in range(-28, -1):
                d = dia(delta, 9)
                if d.weekday() == 6:
                    continue
                for prof in (pa, pb):
                    for hora in sorteio.sample([9, 11, 14, 16], k=sorteio.choice([1, 1, 2])):
                        quando = d.replace(hour=hora)
                        if Agendamento.objects.filter(profissional=prof, data_hora=quando).exists():
                            continue
                        servico = sv[sorteio.choice([s.nome for s in prof.servicos.all()])]
                        status = S.CANCELADO if sorteio.random() < 0.12 else S.CONCLUIDO
                        ag = Agendamento.objects.create(
                            cliente=sorteio.choice(clientes), profissional=prof, servico=servico,
                            data_hora=quando, status=status)
                        if status == S.CONCLUIDO and sorteio.random() < 0.8:
                            chave = prof.usuario.username
                            Avaliacao.objects.get_or_create(agendamento=ag, defaults={
                                "nota": sorteio.choice([5, 5, 5, 4, 4, 3]),
                                "comentario": sorteio.choice(COMENTARIOS[chave] + [""])})

        # avaliações dos atendimentos de exemplo (a coloração da Maria fica sem avaliar,
        # para demonstrar o botão "Avaliar" na área do cliente)
        for cli, prof, servico, nota, chave in ((maria, pa, "Corte feminino", 5, 0), (joao, pb, "Barba completa", 4, 0)):
            ag = Agendamento.objects.filter(
                cliente=cli, profissional=prof, servico=sv[servico], status=S.CONCLUIDO).first()
            if ag:
                Avaliacao.objects.get_or_create(agendamento=ag, defaults={
                    "nota": nota, "comentario": COMENTARIOS[prof.usuario.username][chave]})

        # horários livres para os próximos 14 dias (seg a sáb), sem sobrepor os já existentes.
        # Ana faz coloração (2h), então parte da agenda dela tem blocos de 2 horas.
        grade = {
            pa: [(9, 120), (11, 60), (14, 120), (16, 60), (17, 60)],
            pb: [(9, 60), (10, 60), (11, 60), (14, 60), (15, 60), (16, 60), (17, 60)],
        }
        criados = 0
        for prof, blocos in grade.items():
            for delta in range(1, 15):
                d = base + timedelta(days=delta)
                if d.weekday() == 6:
                    continue
                for hora, minutos in blocos:
                    inicio = d.replace(hour=hora)
                    fim = inicio + timedelta(minutes=minutos)
                    if HorarioDisponivel.objects.filter(
                        profissional=prof, inicio__lt=fim, fim__gt=inicio).exists():
                        continue
                    HorarioDisponivel.objects.create(profissional=prof, inicio=inicio, fim=fim)
                    criados += 1

        # se não houver nenhum atendimento futuro (ex.: banco criado há dias), agenda alguns
        # nos primeiros horários livres, para a agenda do profissional e o painel terem o que mostrar
        agora = timezone.now()
        if not Agendamento.objects.filter(data_hora__gt=agora).exclude(status=S.CANCELADO).exists():
            plano = [
                (maria, pa, "Escova", S.CONFIRMADO, 1), (joao, pb, "Corte masculino", S.PENDENTE, 1),
                (maria, pb, "Manicure", S.PENDENTE, 2), (joao, pa, "Corte masculino", S.CONFIRMADO, 3),
            ]
            for cli, prof, serv, status, dias in plano:
                livre = prof.horarios.futuros().livres().filter(inicio__gte=agora + timedelta(days=dias)).first()
                if livre:
                    Agendamento.objects.create(
                        cliente=cli, profissional=prof, servico=sv[serv], horario=livre, status=status)

        self.stdout.write(self.style.SUCCESS(f"Dados de exemplo prontos! ({criados} horários novos)"))
        self.stdout.write("  Admin:        admin / admin123")
        self.stdout.write("  Profissional: ana / prof12345   (ou bruno / prof12345)")
        self.stdout.write("  Cliente:      maria / cli12345  (ou joao / cli12345)")
