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
Internet Segura, dois instrutores, 30 alunos, os feriados nacionais e sete turmas (todas as
situações), com matrículas, lista de espera, chamadas, certificados e pagamentos (alunos em dia,
pendentes, inadimplentes, bolsistas e um comprovante para conferir). As datas são relativas ao dia em que o
comando roda.

| Usuário | Perfil |
| --- | --- |
| `admin` | Administrador |
| `maria` | Instrutora (Informática Básica, Internet Segura) |
| `carlos` | Instrutor (Excel, Digitação) |
| `aluno` | Aluno com certificado, matrícula ativa e uma mensalidade para pagar com Pix |

A senha de todos é `demo1234` (troque com `--senha`). Se o banco já tiver dados, o comando
para; use `--limpar` para apagar cursos, turmas, alunos, matrículas e certificados e recriar
tudo. Ele se recusa a rodar com `DJANGO_DEBUG=0`.

Sem os dados de demonstração, crie um administrador com `python manage.py createsuperuser`.

## Executável para apresentação (Windows)

O GitHub monta um executável que não precisa de Python instalado: ele sobe o sistema com os
dados de demonstração, funciona sem internet e abre o navegador. Para baixar, abra a página
**Releases** do repositório (também aparece no app do GitHub) e baixe:

- `CursosLivres-Apresentacao-Instalador.exe` (recomendado): instala para o usuário, sem pedir
  administrador, e cria um atalho na Área de Trabalho;
- `CursosLivres-Apresentacao-Portatil.zip`: extraia e abra `Iniciar apresentacao.exe` na pasta.

Link direto para o instalador mais recente:
https://github.com/NOiY-G/Projeto-Escola---Prof.-Claudio-/releases/latest/download/CursosLivres-Apresentacao-Instalador.exe

As instruções de uso estão no `LEIA-ME.txt` (instalado junto, e dentro do .zip).

A montagem roda sozinha quando o código muda (e pode ser disparada à mão, em "Run workflow");
só o que chega na `main` é publicado em Releases (fica só a versão mais recente). Antes de
publicar, o próprio executável é testado, e de novo depois de instalado pelo instalador: sobe o
sistema, abre as telas de cada perfil e gera um certificado em PDF. Sem empacotar, o mesmo lançador roda com
`python apresentacao/iniciar.py` (e `--teste` para só conferir).

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
| `NOME_INSTITUICAO` | Nome no topo dos certificados e recibos (padrão: `Cursos Livres`) |
| `PIX_CHAVE` | Chave Pix da escola, usada no QR Code das parcelas (padrão de exemplo: `pix@exemplo.com`) |
| `PIX_NOME_RECEBEDOR` | Nome do recebedor que aparece no app do banco (até 25 letras) |
| `PIX_CIDADE` | Cidade do recebedor (até 15 letras) |
| `TOLERANCIA_PAGAMENTO_DIAS` | Dias depois do vencimento até o aluno virar inadimplente (padrão: 7) |
| `DJANGO_MEDIA_ROOT` | Pasta dos comprovantes enviados (padrão: `arquivos_privados/`) |
| `DJANGO_EMAIL_BACKEND` | Backend de e-mail para a recuperação de senha (padrão: console) |
| `DJANGO_DEFAULT_FROM_EMAIL` | Remetente dos e-mails |

Os comprovantes enviados pelos alunos ficam em `DJANGO_MEDIA_ROOT` e **não são servidos
publicamente**: só abrem pela aplicação, para o próprio aluno e a administração. Em produção,
use uma pasta que não se perca entre atualizações e inclua-a no backup.

**Antes de usar de verdade, configure `PIX_CHAVE`, `PIX_NOME_RECEBEDOR` e `PIX_CIDADE`** com os
dados da conta da escola; os valores padrão são só de exemplo.

O QR Code do certificado aponta para o domínio pelo qual o sistema foi acessado ao baixar o
PDF; em produção, acesse pelo domínio definitivo.
