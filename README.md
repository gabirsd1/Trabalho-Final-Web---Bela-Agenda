# BelaAgenda

Sistema web de **agendamento e atendimento para salão de beleza**, desenvolvido com Django
para a disciplina **GAC116 – Programação Web** (Trabalho Prático).

## Integrantes

- Gabriela Ribeiro Silveira
- Larissa Rocha Silva

## Descrição do projeto

O BelaAgenda permite que clientes escolham um serviço, um profissional e um horário para ser atendidos,
que profissionais acompanhem e conduzam a própria agenda e que a administração gerencie o salão
(cadastros, usuários, relatórios de faturamento).

Existem três perfis de usuário, cada um com sua área protegida por login:

| Perfil | O que pode fazer |
|---|---|
| **Cliente** | Criar conta, agendar, ver, filtrar e cancelar os próprios agendamentos |
| **Profissional** | Ver a agenda do dia, confirmar, concluir ou cancelar atendimentos |
| **Administrador** | Painel de gestão (faturamento, serviços mais pedidos) e Django Admin completo |

## Tecnologias utilizadas

- Python 3 e **Django** (arquitetura MVT, CBVs, ORM, autenticação)
- **SQLite** (banco relacional)
- **django-jazzmin** (tema do ambiente administrativo)
- **Bootstrap 5.3** + Bootstrap Icons (interface responsiva, tema claro e escuro)
- **Pillow** (upload de fotos dos profissionais)
- Git e GitHub (`main`, `develop` e branches `feature/*`)

## Instruções para instalação

```bash
git clone <URL-DO-REPOSITORIO>
cd belaagenda

python -m venv venv
source venv/bin/activate          
pip install -r requirements.txt
python manage.py migrate
python manage.py popular         
```

## Instruções para execução

```bash
python manage.py runserver
```

Acesse http://127.0.0.1:8000/ (site) e http://127.0.0.1:8000/admin/ (administração).

Para rodar os testes automatizados: `python manage.py test`

### Usuários criados pelo comando `popular`

| Perfil | Usuário | Senha |
|---|---|---|
| Administrador | `admin` | `admin123` |
| Profissional | `ana` / `bruno` | `prof12345` |
| Cliente | `maria` / `joao` | `cli12345` |

Sem usar o `popular`, crie o administrador com `python manage.py createsuperuser`.

## Principais funcionalidades

- Cadastro público (sempre cria **Cliente**), login e logout
- Redirecionamento automático para a área de cada perfil e controle de acesso (403 para perfil indevido)
- Agendamento com **regras de negócio**: sem horários no passado, sem domingos, expediente 08h–19h,
  profissional deve realizar o serviço, sem sobreposição de horários (considera a duração do serviço)
- Lista de serviços do formulário carregada dinamicamente conforme o profissional escolhido (fetch/JSON)
- Preço gravado no momento do agendamento (histórico de faturamento correto)
- Agenda do profissional por dia, com fluxo de status: Pendente → Confirmado → Concluído (ou Cancelado)
- Painel de gestão com filtro por período: faturamento, valor a receber, ranking de serviços e profissionais
- Django Admin com tema Jazzmin, busca, `list_filter`, filtro personalizado de período e hierarquia por data
- Tema claro/escuro com botão de alternância (lembra a escolha) e layout responsivo

## Estrutura do projeto

```
belaagenda/
├── manage.py
├── requirements.txt
├── config/                  # settings, urls, wsgi/asgi
├── accounts/                # app 1: usuários, login, cadastro, perfis
│   ├── models.py            #   Usuario (AbstractUser + perfil)
│   ├── forms.py             #   LoginForm, CadastroForm
│   ├── mixins.py            #   PerfilRequiredMixin (controle de acesso)
│   ├── views.py / urls.py
│   └── admin.py
├── salao/                   # app 2: regras do salão
│   ├── models.py            #   Categoria, Servico, Profissional, Agendamento
│   ├── forms.py / views.py / urls.py
│   ├── admin.py             #   filtros do Django Admin
│   ├── tests.py             #   testes automatizados
│   └── management/commands/popular.py
├── templates/               # base.html, login, cadastro, telas por perfil
└── static/                  # css/app.css, js/theme.js
```

### Modelagem

`Usuario` 1—1 `Profissional` N—N `Servico` N—1 `Categoria`.
`Agendamento` liga `Usuario` (cliente), `Profissional` e `Servico`.

## Fluxo de Git

`main` (versão estável) ← `develop` (integração) ← `feature/*` (uma por funcionalidade).
