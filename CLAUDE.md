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
  turmas/          # Turma, Aula, Feriado
  alunos/          # Aluno
  matriculas/      # Matricula, Frequencia
  certificados/    # geração e validação de certificados
  relatorios/      # painéis e exportações
  financeiro/      # Parcela, Pagamento, Comprovante
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
- frequencia_minima (%, padrão 75), parcelas_max (1 a 12, padrão 1 = só à vista), ativo (bool), criado_em

**Instrutor**
- usuario (OneToOne User), nome, telefone, especialidades

**Turma**
- curso (FK), instrutor (FK), codigo (ex.: `INF-2026-01`, único)
- data_inicio, data_fim, dias_semana (ex.: seg/qua), hora_inicio, hora_fim
- sala, vagas (inteiro > 0), status: `planejada | inscricoes_abertas | em_andamento | concluida | cancelada`

**Aula**
- turma (FK), data, conteudo (texto)
- Gerar as aulas automaticamente a partir das datas e dias da semana da turma, pulando os feriados.

**Feriado**
- data (única), descricao. Dia sem aula para todas as turmas (também recesso e ponto facultativo).

**Aluno**
- usuario (OneToOne User, opcional), nome, cpf (único, validado), data_nascimento
- telefone, email, endereco, escolaridade, criado_em

**Matricula**
- aluno (FK), turma (FK), data, status: `ativa | lista_espera | concluida | desistente | cancelada`
- n_parcelas (padrão 1), desconto (%, 0 a 100; 100 = bolsa integral)
- Único por (aluno, turma).

**Frequencia**
- matricula (FK), aula (FK), presente (bool), observacao
- Único por (matricula, aula).

**Certificado**
- matricula (OneToOne), codigo_validacao (UUID), emitido_em

**Parcela**
- matricula (FK), numero, valor, vencimento, status: `aberta | em_analise | paga | cancelada`
- Único por (matricula, numero). Identificador no Pix: `PARC` + id com 6 dígitos.

**Pagamento**
- parcela (FK), valor, data, forma: `pix | dinheiro`, codigo_transacao (Pix, opcional, único entre não estornados)
- observacao, comprovante (OneToOne, opcional), recebido_por (User), registrado_em, estornado_em, motivo_estorno
- Nunca é apagado: correção é por estorno.

**Comprovante**
- parcela (FK), arquivo (JPG, PNG ou PDF, até 5 MB, nome aleatório), tipo_conteudo, enviado_em, enviado_por
- status: `em_analise | aprovado | recusado`, motivo_recusa, analisado_em, analisado_por

## Regras de negócio

1. Só é possível matricular em turma com status `inscricoes_abertas`.
2. Se a turma estiver cheia, a matrícula entra como `lista_espera`. Quando uma vaga abrir (desistência ou cancelamento), o primeiro da fila vira `ativa` automaticamente.
3. Um aluno não pode ter duas matrículas ativas em turmas com horários conflitantes.
4. Percentual de frequência = presenças / aulas já realizadas × 100.
5. Ao concluir a turma, matrículas ativas com frequência ≥ frequência mínima do curso viram `concluida` e ganham certificado. As demais viram `desistente`.
6. O certificado em PDF traz nome do aluno, CPF parcialmente mascarado, curso, carga horária, período e um QR Code apontando para `/certificados/validar/<codigo>/`.
7. A página de validação é pública e mostra apenas se o certificado é válido e seus dados básicos.
8. As parcelas são geradas quando a matrícula fica ativa (na matrícula ou ao sair da fila): valor do curso − desconto, dividido em `n_parcelas` (até `parcelas_max` do curso; centavos que sobram vão para a última). A 1ª vence no início da turma (ou hoje, se já começou) e as demais a cada 30 dias. Curso gratuito ou bolsa integral não gera parcelas (isento).
9. Cancelamento ou desistência cancelam as parcelas que ainda não venceram (as que vencem hoje inclusive). As vencidas continuam em aberto.
10. Situação financeira da matrícula: `isento`, `em dia`, `pendente` (parcela vencida há até `TOLERANCIA_PAGAMENTO_DIAS`, padrão 7) ou `inadimplente` (vencida há mais que isso). Parcela com comprovante em análise não conta como vencida. O sistema só avisa (chamada, painel, ficha do aluno); não bloqueia.
11. Só Pix e dinheiro. O pagamento quita a parcela inteira; data no futuro é recusada; o mesmo código de transação Pix não quita duas parcelas. Estorno exige motivo e devolve a parcela para `aberta`.
12. O aluno paga pelo Pix "copia e cola" gerado pelo sistema (chave, valor e identificador da parcela, sem API) e envia o comprovante. A secretaria confere no extrato e aprova (vira pagamento Pix) ou recusa com motivo (o aluno vê o motivo e pode reenviar). Comprovantes só são acessíveis ao próprio aluno e à administração.
13. O certificado não depende da situação financeira.

## Telas

- **Login** e recuperação de senha
- **Painel** com números do dia: turmas em andamento, vagas livres, matrículas recentes
- **Cursos:** listar, criar, editar, ativar/desativar
- **Turmas:** listar com filtro por status e curso, criar, editar, ver alunos
- **Alunos:** listar com busca por nome ou CPF, criar, editar, histórico de cursos
- **Matrículas:** matricular aluno em turma, ver lista de espera
- **Chamada:** instrutor escolhe a aula e marca presença de todos em uma tela só (HTMX)
- **Certificados:** emitir, baixar PDF, validar
- **Feriados:** cadastrar, remover e cadastrar os feriados nacionais do ano
- **Pagamentos:** parcelas por filtro (comprovantes para conferir, vencidas, a vencer, pagas no mês), registrar pagamento, conferir comprovante; aba Financeiro na ficha do aluno (pagamentos, recibo, estorno); Pix e envio de comprovante em "Minhas matrículas"
- **Relatórios:** alunos por curso, taxa de conclusão, evasão e ocupação das turmas, financeiro por mês (Pix, dinheiro, previsto, em aberto), com exportação em CSV

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
