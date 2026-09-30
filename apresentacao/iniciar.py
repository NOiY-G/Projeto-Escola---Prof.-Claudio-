"""Inicia o sistema para apresentação: dados de demonstração + navegador aberto.

É o ponto de entrada do executável (PyInstaller), mas também roda direto:
    python apresentacao/iniciar.py            # apresentação
    python apresentacao/iniciar.py --teste    # confere se tudo funciona e sai

A cada início os dados de demonstração são recriados, com datas do dia.
Use --manter-dados para continuar de onde parou.
"""

import argparse
import io
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)
# Onde estão o código e os templates (dentro do executável ou a raiz do projeto).
PASTA_PROGRAMA = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
# Onde ficam banco e comprovantes: ao lado do executável (ou em .apresentacao/ no projeto).
PASTA_DADOS = (
    Path(sys.executable).resolve().parent / "dados-da-apresentacao"
    if CONGELADO
    else PASTA_PROGRAMA / ".apresentacao"
)
SENHA = "demo1234"


def ip_na_rede():
    """IP deste computador na rede local (para abrir no celular), ou None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # não envia nada; só escolhe a interface
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def porta_livre(preferida=8000):
    for porta in [preferida, *range(8001, 8100)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise SystemExit("Nenhuma porta livre entre 8000 e 8099.")


def reiniciar_com_ambiente_do_pdf():
    """No Windows empacotado, reinicia o programa com as variáveis das bibliotecas de PDF.

    As bibliotecas em C (fontconfig) leem o ambiente só quando o processo começa, então
    definir as variáveis depois, pelo Python, não adianta. Sem isso a janela mostraria
    "Fontconfig error" e o PDF usaria a configuração reserva (mais lenta).
    """
    gtk = PASTA_PROGRAMA / "gtk"
    if not (CONGELADO and gtk.is_dir()) or os.environ.get("CURSOS_LIVRES_REINICIADO"):
        return
    fontes = gtk / "etc" / "fonts"
    ambiente = dict(
        os.environ,
        CURSOS_LIVRES_REINICIADO="1",
        FONTCONFIG_PATH=str(fontes),
        FONTCONFIG_FILE=str(fontes / "fonts.conf"),
    )
    try:
        sys.exit(subprocess.call([sys.executable, *sys.argv[1:]], env=ambiente))
    except KeyboardInterrupt:
        sys.exit(0)


def configurar_ambiente(ip, teste):
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(PASTA_PROGRAMA))
    hosts = ["127.0.0.1", "localhost"] + ([ip] if ip else []) + (["testserver"] if teste else [])
    padrao = {
        "DJANGO_SETTINGS_MODULE": "cursos.settings",
        "DATABASE_URL": f"sqlite:///{(PASTA_DADOS / 'demo.sqlite3').as_posix()}",
        "DJANGO_MEDIA_ROOT": str(PASTA_DADOS / "comprovantes"),
        "DJANGO_DEBUG": "1",  # servidor local de demonstração
        "DJANGO_ALLOWED_HOSTS": ",".join(hosts),
        "USAR_CDN": "0",  # Tailwind e HTMX locais: funciona sem internet
    }
    for chave, valor in padrao.items():
        os.environ.setdefault(chave, valor)
    gtk = PASTA_PROGRAMA / "gtk"
    if gtk.is_dir():
        # Bibliotecas do WeasyPrint (PDF) empacotadas junto no Windows.
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(gtk / "bin")
    import django

    django.setup()


def preparar_dados(manter):
    from django.core.management import call_command
    from django.core.management.commands.migrate import Command as Migrate

    from apps.catalogo.management.commands.popular_demo import Command as PopularDemo
    from apps.catalogo.models import Curso

    print("Preparando o banco de dados...", flush=True)
    call_command(Migrate(), verbosity=0, interactive=False)
    if manter and Curso.objects.exists():
        print("Mantendo os dados da última apresentação.", flush=True)
        return
    print("Criando os dados de demonstração (com as datas de hoje)...", flush=True)
    call_command(PopularDemo(), limpar=True, senha=SENHA, verbosity=0, stdout=io.StringIO())


def iniciar_servidor(porta):
    from django.contrib.staticfiles.management.commands.runserver import Command as Runserver
    from django.core.management import call_command

    call_command(Runserver(), f"0.0.0.0:{porta}", use_reloader=False, use_threading=True, skip_checks=True)


def esperar_servidor(url, segundos=30):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except OSError:
            time.sleep(0.3)
    return False


def conferir(porta):
    """Modo --teste: sobe o servidor e confere telas, arquivos locais e PDF."""
    from django.test import Client

    from apps.certificados.models import Certificado
    from apps.certificados.services import html_do_certificado

    base = f"http://127.0.0.1:{porta}"
    threading.Thread(target=iniciar_servidor, args=(porta,), daemon=True).start()
    falhas = []

    def ok(condicao, descricao):
        print(("  OK    " if condicao else "  FALHA ") + descricao, flush=True)
        if not condicao:
            falhas.append(descricao)

    ok(esperar_servidor(base + "/entrar/"), "servidor respondeu em " + base)
    for caminho in ["/entrar/", "/static/vendor/tailwindcss.js", "/static/vendor/htmx.min.js", "/static/admin/css/base.css"]:
        try:
            status = urllib.request.urlopen(base + caminho, timeout=10).status
        except OSError as erro:
            status = erro
        ok(status == 200, f"GET {caminho} -> {status}")

    cliente = Client()
    for usuario, paginas in {
        "admin": ["/", "/catalogo/cursos/", "/turmas/", "/alunos/", "/financeiro/", "/relatorios/financeiro/", "/turmas/feriados/"],
        "carlos": ["/", "/turmas/"],
        "aluno": ["/matriculas/minhas/"],
    }.items():
        ok(cliente.login(username=usuario, password=SENHA), f"login de {usuario}")
        for pagina in paginas:
            status = cliente.get(pagina).status_code
            ok(status == 200, f"{usuario} abre {pagina} -> {status}")
    resposta = cliente.get("/matriculas/minhas/").content.decode()
    ok("data:image/png;base64," in resposta, "QR Code do Pix aparece para o aluno")

    try:
        from weasyprint import HTML

        certificado = Certificado.objects.first()
        documento = HTML(string=html_do_certificado(certificado, base + "/certificados/validar/teste/")).render()
        pdf = documento.write_pdf()
        ok(pdf.startswith(b"%PDF"), f"PDF do certificado gerado ({len(pdf) // 1024} KB)")
        # Sem fontes encontradas (fontconfig), o PDF sai sem texto: conferir que alguma foi usada.
        ok(len(documento.fonts) > 0, f"texto no PDF ({len(documento.fonts)} fonte(s) usada(s))")
        (PASTA_DADOS / "certificado-teste.pdf").write_bytes(pdf)
    except Exception as erro:  # o PDF é o ponto mais frágil no Windows
        ok(False, f"PDF do certificado: {erro!r}")

    print(("\nTudo certo." if not falhas else f"\n{len(falhas)} falha(s).") , flush=True)
    return 0 if not falhas else 1


def main():
    parser = argparse.ArgumentParser(description="Apresentação do sistema Cursos Livres")
    parser.add_argument("--teste", action="store_true", help="confere se tudo funciona e sai")
    parser.add_argument("--manter-dados", action="store_true", help="não recria os dados de demonstração")
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()

    reiniciar_com_ambiente_do_pdf()
    ip = ip_na_rede()
    configurar_ambiente(ip, args.teste)
    preparar_dados(args.manter_dados)
    porta = porta_livre(args.porta)

    if args.teste:
        sys.exit(conferir(porta))

    endereco = f"http://{ip or '127.0.0.1'}:{porta}"
    print(
        f"""
==============================================================
  Cursos Livres - apresentação
==============================================================
  Abra no navegador:   {endereco}
  No celular (mesma rede Wi-Fi): {endereco if ip else 'sem rede no momento'}

  Usuários (senha {SENHA}):
    admin   Administrador
    maria   Instrutora
    carlos  Instrutor
    aluno   Aluno (tem certificado e mensalidade para pagar com Pix)

  Para encerrar, feche esta janela.
==============================================================
""",
        flush=True,
    )
    threading.Timer(1.5, webbrowser.open, args=[endereco + "/entrar/"]).start()
    iniciar_servidor(porta)


if __name__ == "__main__":
    main()
