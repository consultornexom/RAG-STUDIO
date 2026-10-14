# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para RAG STUDIO -- ítem 7 de la segunda
evaluación de madurez post-8-etapas (ver bitácora en README).

Uso (desde la raíz del repo, con `pip install -r requirements.txt` ya
instalado -- incluye pyinstaller y las dependencias de UI):

    pyinstaller packaging/ragstudio.spec --noconfirm --clean

Produce `dist/RAGStudio/` (modo onedir: una carpeta con el ejecutable y
sus bibliotecas -- arranca más rápido y es más fácil de depurar que
onefile). El resultado es válido SOLO para el sistema operativo donde
se corrió `pyinstaller`: para Windows hay que correr esto en Windows,
para macOS en macOS -- PyInstaller nunca hace compilación cruzada real.

Este .spec se construyó y se verificó en Linux dentro del entorno de
construcción de este proyecto (ver bitácora): el ejecutable resultante
arranca de verdad con `QT_QPA_PLATFORM=offscreen` (sin servidor
gráfico), corre las migraciones Alembic reales, y se apaga limpio.
Sigue sin haber verificación real en Windows/macOS, ni firma de código,
ni un instalador de verdad (`.msi`/`.dmg`/`.deb` -- herramientas
específicas de cada sistema operativo, fuera de alcance de este .spec) --
ver "Limitaciones conocidas" en README para el detalle honesto de qué
falta todavía.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# packaging/ vive un nivel bajo la raíz del repo.
REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH lo inyecta PyInstaller

datas = [
    (str(REPO_ROOT / "ui" / "LOGO.png"), "ui"),
    # migrations/ (env.py + versions/*.py de las 2 líneas de Alembic,
    # global y por proyecto) -- infrastructure.database.migrations
    # busca esta carpeta también dentro de sys._MEIPASS cuando la app
    # corre congelada (ver ese módulo, mismo ítem).
    (str(REPO_ROOT / "migrations"), "migrations"),
]

hiddenimports = [
    "alembic",
    "sqlalchemy.dialects.sqlite",
    "qdrant_client",
    "qdrant_client.local",
    "fastembed",
    "onnxruntime",
    "keyring.backends",
    # tiktoken registra sus codificaciones (cl100k_base, etc.) vía
    # plugins descubiertos con pkgutil.iter_modules en tiktoken_ext/ --
    # PyInstaller no lo detecta caminando imports normales, hay que
    # pedirle explícitamente que junte todos los submódulos (gotcha
    # documentado de tiktoken + PyInstaller).
    *collect_submodules("tiktoken_ext"),
]

a = Analysis(  # noqa: F821 - clases inyectadas por el runtime de PyInstaller
    [str(REPO_ROOT / "run_app.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RAGStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RAGStudio",
)
