# Empacotamento do executável de apresentação (PyInstaller).
#
#   pyinstaller apresentacao/cursos_livres.spec
#
# No Windows, defina GTK_DIR com uma pasta que tenha bin/ (DLLs do Pango/GTK) e
# etc/fonts/ (fontconfig) para o PDF funcionar; o workflow do GitHub faz isso.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

raiz = Path(SPECPATH).parent

# Os apps do projeto são carregados pelo nome (INSTALLED_APPS, urls, migrações):
# o PyInstaller não os acha sozinho, então listamos todos os módulos.
modulos = []
for pasta in ("apps", "cursos"):
    for arquivo in (raiz / pasta).rglob("*.py"):
        partes = arquivo.relative_to(raiz).with_suffix("").parts
        modulos.append(".".join(partes[:-1] if partes[-1] == "__init__" else partes))

datas = [
    (str(raiz / "templates"), "templates"),
    (str(raiz / "static"), "static"),
    *collect_data_files("weasyprint"),
    *collect_data_files("django"),
]
if os.environ.get("GTK_DIR"):
    datas.append((os.environ["GTK_DIR"], "gtk"))

a = Analysis(
    [str(raiz / "apresentacao" / "iniciar.py")],
    pathex=[str(raiz)],
    hiddenimports=modulos
    + [
        "django.contrib.staticfiles.management.commands.runserver",
        "django.core.management.commands.migrate",
    ],
    datas=datas,
    excludes=["psycopg", "psycopg_binary", "pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Iniciar apresentacao",
    console=True,  # a janela mostra o endereço e os usuários; fechá-la encerra o sistema
)
coll = COLLECT(exe, a.binaries, a.datas, name="CursosLivres-Apresentacao")
