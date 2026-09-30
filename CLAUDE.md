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
- duracao_meses (1 a 36; também é o número de mensalidades), horas_por_aula (decimal, ex.: 2 ou 1,5)
- pre_requisitos (texto, opcional), valor_mensalidade (decimal, 0 = gratuito)
- frequencia_minima (%, padrão 75), ativo (bool), criado_em

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
- desconto (%, 0 a 100, vale para todas as mensalidades; 100 = bolsa integral)
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
8. O curso é cobrado por mensalidade (não há valor total nem parcelamento). As mensalidades (modelo `Parcela`) são geradas quando a matrícula fica ativa (na matrícula ou ao sair da fila): uma por mês de `duracao_meses`, no valor da mensalidade − desconto. A 1ª vence no início da turma e as demais no mesmo dia dos meses seguintes (dia 31 vira o último dia do mês). Quem entra com a turma em andamento não paga os meses já encerrados; a do mês em curso vence hoje. Curso gratuito ou bolsa integral não gera mensalidades (isento).
9. Cancelamento ou desistência cancelam as parcelas que ainda não venceram (as que vencem hoje inclusive). As vencidas continuam em aberto.
10. Situação financeira da matrícula: `isento`, `em dia`, `pendente` (parcela vencida há até `TOLERANCIA_PAGAMENTO_DIAS`, padrão 7) ou `inadimplente` (vencida há mais que isso). Parcela com comprovante em análise não conta como vencida. O sistema só avisa (chamada, painel, ficha do aluno); não bloqueia.
11. Só Pix e dinheiro. O pagamento quita a parcela inteira; data no futuro é recusada; o mesmo código de transação Pix não quita duas parcelas. Estorno exige motivo e devolve a parcela para `aberta`.
12. O aluno paga pelo Pix "copia e cola" gerado pelo sistema (chave, valor e identificador da parcela, sem API) e envia o comprovante. A secretaria confere no extrato e aprova (vira pagamento Pix) ou recusa com motivo (o aluno vê o motivo e pode reenviar). Comprovantes só são acessíveis ao próprio aluno e à administração.
13. O certificado não depende da situação financeira.
14. Carga horária: no cadastro do curso o administrador informa a carga horária, a duração em meses e a duração da aula. O sistema calcula o mínimo de dias de aula por semana, contando de segunda a sábado e cada mês como 4 semanas: aulas = carga ÷ duração da aula (para cima); dias mínimos = aulas ÷ (meses × 4) (para cima). Se passar de 6 dias, o cadastro é recusado. Na matrícula o sistema informa os dias mínimos do curso e se o calendário da turma (aulas sem feriados × duração da aula da turma) cumpre a carga horária; se não cumprir, avisa (na turma e na matrícula), sem bloquear.
15. Ao criar a turma, se a data de término ficar em branco ela é calculada pela duração do curso.

## Telas

- **Login** e recuperação de senha
- **Painel** com números do dia: turmas em andamento, vagas livres, matrículas recentes
- **Cursos:** listar, criar, editar (com prévia dos dias mínimos por semana), ativar/desativar
- **Turmas:** listar com filtro por status e curso, criar, editar, ver alunos
- **Alunos:** listar com busca por nome ou CPF, criar, editar, histórico de cursos
- **Matrículas:** matricular aluno em turma (mostrando os dias mínimos por semana, a carga prevista da turma e as mensalidades), ver lista de espera
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
