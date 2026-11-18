# BelaAgenda · novidades do Checkpoint 2

## O que mudou
- **Horários cadastrados pelo profissional.** O profissional gera horários em blocos (ex.: 09h às 12h, 1 hora cada)
  em `/profissional/horarios/`. O cliente só escolhe entre os horários livres; ninguém digita data e hora.
- **Novo agendamento em 4 etapas** (profissional → serviço → dia e horário → recado), com resumo ao lado, tudo em português.
  Só aparecem horários livres que comportam a duração do serviço escolhido. Cancelar libera o horário.
- **Perfil do profissional**: foto, especialidade, anos de experiência e texto de apresentação
  (edição em `/profissional/perfil/`, página pública em `/profissionais/<id>/`).
- **Avaliações**: depois de um atendimento concluído, o cliente dá nota de 1 a 5 e comentário
  (`/cliente/agendamentos/<id>/avaliar/`). A média aparece na home, no perfil, na agenda e no painel.
- **Painel de gestão** (`/gestao/`) com indicadores (faturamento, ticket médio, cancelamento, satisfação),
  gráficos (receita por dia, status, serviços mais pedidos), ranking de profissionais com nota,
  últimas avaliações e próximos atendimentos. Os gráficos acompanham o tema claro/escuro.
- **Admin (Jazzmin)**: novas telas *Horários disponíveis* (filtro Livres/Reservados e por data) e *Avaliações* (filtro por nota e profissional).

## Novos modelos
`HorarioDisponivel` (profissional, início, fim) e `Avaliacao` (agendamento 1:1, nota, comentário).
`Profissional` ganhou `descricao` e `anos_experiencia`; `Agendamento` ganhou `horario` (FK).
Regra no banco: um horário só pode ter um agendamento ativo.

## Como atualizar
    python manage.py migrate     # liga os agendamentos antigos aos novos horários
    python manage.py popular     # cria horários, avaliações e histórico de exemplo
    python manage.py test        # 58 testes
