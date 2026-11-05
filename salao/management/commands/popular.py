from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Usuario
from salao.models import Agendamento, Categoria, Profissional, Servico

P = Usuario.Perfil
S = Agendamento.Status


class Command(BaseCommand):
    help = "Cria dados de exemplo (usuários, serviços e agendamentos) para testar o sistema."

    def handle(self, *args, **opts):
        def usuario(username, senha, **extra):
            u, criado = Usuario.objects.get_or_create(username=username, defaults=extra)
            if criado:
                u.set_password(senha)
                u.save()
            return u

        admin = usuario("admin", "admin123", first_name="Gerente", last_name="Bela",
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

        if not Agendamento.objects.exists():
            base = timezone.localtime().replace(minute=0, second=0, microsecond=0)

            def dia(delta, hora):
                d = base + timedelta(days=delta)
                if d.weekday() == 6:  # pula domingo
                    d += timedelta(days=1)
                return d.replace(hour=hora)

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
                Agendamento.objects.create(cliente=cli, profissional=prof, servico=sv[serv],
                                           data_hora=quando, status=status)

        self.stdout.write(self.style.SUCCESS("Dados de exemplo prontos!"))
        self.stdout.write("  Admin:        admin / admin123")
        self.stdout.write("  Profissional: ana / prof12345   (ou bruno / prof12345)")
        self.stdout.write("  Cliente:      maria / cli12345  (ou joao / cli12345)")
