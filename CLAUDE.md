# Sistema de Cadastro de Cursos Livres

Sistema web para gerenciar cursos livres (Informática Básica, Excel, Digitação etc.), turmas, alunos, matrículas, frequência e certificados.

## Stack

- **Backend:** Python 3.12 + Django 5
- **Banco:** SQLite em desenvolvimento, PostgreSQL em produção (via `DATABASE_URL`)
- **Front-end:** templates Django + HTMX + Tailwind CSS (via CDN no início)
- **PDF:** WeasyPrint para certificados
- **Testes:** pytest + pytest-django
- **Idioma e fuso:** `LANGUAGE_CODE = "pt-br"`, `TIME_ZONE = "America/Belem"`

## Estrutura de pastas

```
cursos/            # projeto Django (settings, urls)
apps/
  contas/          # usuários e perfis
  catalogo/        # Curso, Instrutor
  turmas/          # Turma, Aula
  alunos/          # Aluno
  matriculas/      # Matricula, Frequencia
  certificados/    # geração e validação de certificados
  relatorios/      # painéis e exportações
templates/
static/
tests/
```

## Perfis de acesso

Usar grupos do Django:

- **Administrador:** acesso total, incluindo relatórios.
- **Instrutor:** vê apenas as próprias turmas, faz a chamada e lança observações.
- **Aluno:** vê as próprias matrículas, frequência e baixa certificados.

## Modelo de dados

**Curso**
- nome (único), descricao, carga_horaria (horas, inteiro > 0)
- pre_requisitos (texto, opcional), valor (decimal, 0 = gratuito)
- frequencia_minima (%, padrão 75), ativo (bool), criado_em

**Instrutor**
- usuario (OneToOne User), nome, telefone, especialidades

**Turma**
- curso (FK), instrutor (FK), codigo (ex.: `INF-2026-01`, único)
- data_inicio, data_fim, dias_semana (ex.: seg/qua), hora_inicio, hora_fim
- sala, vagas (inteiro > 0), status: `planejada | inscricoes_abertas | em_andamento | concluida | cancelada`

**Aula**
- turma (FK), data, conteudo (texto)
- Gerar as aulas automaticamente a partir das datas e dias da semana da turma.

**Aluno**
- usuario (OneToOne User, opcional), nome, cpf (único, validado), data_nascimento
- telefone, email, endereco, escolaridade, criado_em

**Matricula**
- aluno (FK), turma (FK), data, status: `ativa | lista_espera | concluida | desistente | cancelada`
- Único por (aluno, turma).

**Frequencia**
- matricula (FK), aula (FK), presente (bool), observacao
- Único por (matricula, aula).

**Certificado**
- matricula (OneToOne), codigo_validacao (UUID), emitido_em

## Regras de negócio

1. Só é possível matricular em turma com status `inscricoes_abertas`.
2. Se a turma estiver cheia, a matrícula entra como `lista_espera`. Quando uma vaga abrir (desistência ou cancelamento), o primeiro da fila vira `ativa` automaticamente.
3. Um aluno não pode ter duas matrículas ativas em turmas com horários conflitantes.
4. Percentual de frequência = presenças / aulas já realizadas × 100.
5. Ao concluir a turma, matrículas ativas com frequência ≥ frequência mínima do curso viram `concluida` e ganham certificado. As demais viram `desistente`.
6. O certificado em PDF traz nome do aluno, CPF parcialmente mascarado, curso, carga horária, período e um QR Code apontando para `/certificados/validar/<codigo>/`.
7. A página de validação é pública e mostra apenas se o certificado é válido e seus dados básicos.

## Telas

- **Login** e recuperação de senha
- **Painel** com números do dia: turmas em andamento, vagas livres, matrículas recentes
- **Cursos:** listar, criar, editar, ativar/desativar
- **Turmas:** listar com filtro por status e curso, criar, editar, ver alunos
- **Alunos:** listar com busca por nome ou CPF, criar, editar, histórico de cursos
- **Matrículas:** matricular aluno em turma, ver lista de espera
- **Chamada:** instrutor escolhe a aula e marca presença de todos em uma tela só (HTMX)
- **Certificados:** emitir, baixar PDF, validar
- **Relatórios:** alunos por curso, taxa de conclusão, evasão e ocupação das turmas, com exportação em CSV

Todas as telas devem funcionar bem no celular.

## Ordem de desenvolvimento

1. Projeto Django, apps, settings, Tailwind, login e grupos de perfil
2. Modelos, migrações e Django Admin para todos os modelos
3. CRUD de cursos, instrutores, turmas e alunos
4. Matrículas com controle de vagas e lista de espera
5. Geração de aulas e tela de chamada
6. Conclusão de turma e certificados em PDF com QR Code
7. Relatórios e exportação CSV
8. Comando `python manage.py popular_demo` com dados de exemplo (cursos de Informática Básica, Excel, Digitação, Internet Segura)

## Convenções

- Código e nomes de modelos em português, sem acentos nos identificadores.
- Regras de negócio em `services.py` de cada app, nunca nas views.
- Toda regra de negócio acima precisa de teste.
- Rodar `pytest` antes de considerar uma etapa concluída.
- Datas no formato brasileiro (dd/mm/aaaa) e valores em R$.
