# Sistema de Cadastro de Cursos Livres

Sistema web para gerenciar cursos livres, turmas, alunos, matrículas, frequência e certificados.
Veja as especificações completas em [CLAUDE.md](CLAUDE.md).

## Como rodar

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate          # também cria os grupos Administrador, Instrutor e Aluno
python manage.py createsuperuser
python manage.py runserver
```

Acesse http://127.0.0.1:8000/ para o sistema e http://127.0.0.1:8000/admin/ para o Django Admin.

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
