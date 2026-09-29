# Sistema de Cadastro de Cursos Livres

Sistema web para gerenciar cursos livres, turmas, alunos, matrículas, frequência e certificados.
Veja as especificações completas em [CLAUDE.md](CLAUDE.md).

## Como rodar

O PDF dos certificados usa o WeasyPrint, que precisa das bibliotecas Pango instaladas no
sistema (no Debian/Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`; veja a
[documentação do WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)
para outros sistemas).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate          # também cria os grupos Administrador, Instrutor e Aluno
python manage.py popular_demo     # dados de exemplo (opcional)
python manage.py runserver
```

Acesse http://127.0.0.1:8000/ para o sistema e http://127.0.0.1:8000/admin/ para o Django Admin.

### Dados de demonstração

`python manage.py popular_demo` cria os cursos Informática Básica, Excel, Digitação e
Internet Segura, dois instrutores, 30 alunos, os feriados nacionais e seis turmas (uma em
cada situação), com matrículas, lista de espera, chamadas e certificados. As datas são relativas ao dia em que o
comando roda.

| Usuário | Perfil |
| --- | --- |
| `admin` | Administrador |
| `maria` | Instrutora (Informática Básica, Internet Segura) |
| `carlos` | Instrutor (Excel, Digitação) |
| `aluno` | Aluno com certificado e matrícula ativa |

A senha de todos é `demo1234` (troque com `--senha`). Se o banco já tiver dados, o comando
para; use `--limpar` para apagar cursos, turmas, alunos, matrículas e certificados e recriar
tudo. Ele se recusa a rodar com `DJANGO_DEBUG=0`.

Sem os dados de demonstração, crie um administrador com `python manage.py createsuperuser`.

## Testes

```bash
pytest
```

## Variáveis de ambiente (produção)

| Variável | Descrição |
| --- | --- |
| `DATABASE_URL` | Ex.: `postgres://usuario:senha@host:5432/cursos` (padrão: SQLite local) |
| `DJANGO_SECRET_KEY` | Chave secreta |
| `DJANGO_DEBUG` | `0` em produção |
| `DJANGO_ALLOWED_HOSTS` | Hosts separados por vírgula |
| `NOME_INSTITUICAO` | Nome no topo dos certificados (padrão: `Cursos Livres`) |
| `DJANGO_EMAIL_BACKEND` | Backend de e-mail para a recuperação de senha (padrão: console) |
| `DJANGO_DEFAULT_FROM_EMAIL` | Remetente dos e-mails |

O QR Code do certificado aponta para o domínio pelo qual o sistema foi acessado ao baixar o
PDF; em produção, acesse pelo domínio definitivo.
