"""Ejecuta las migraciones Alembic de las dos líneas independientes
(global y por proyecto) contra un archivo SQLite concreto.

No requiere un alembic.ini en disco: construye el Config en memoria y
fija sqlalchemy.url según la instalación o el proyecto en cuestión.
"""
from __future__ import annotations

import sys
import os
import threading
from pathlib import Path

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory

# _ALEMBIC_LOCK (auditoría Ronda 10, hallazgo descubierto al escribir
# la prueba de concurrencia del hallazgo A2, ver
# tests/integration/test_runtime_api_concurrency.py): `alembic.command.
# upgrade/downgrade` instala temporalmente un proxy en variables
# GLOBALES del módulo `alembic.context` durante su ejecución y lo
# retira en su `__exit__` -- eso no es seguro si dos hilos del mismo
# proceso llaman a `command.upgrade` al mismo tiempo (un hilo puede
# retirar el proxy que el otro todavía está usando, o intentar
# retirarlo dos veces: `KeyError: 'config'`). `ensure_project_db` se
# invoca en la práctica desde cada apertura de repositorio -- en el
# runtime de producción, en cada solicitud HTTP, servida en el
# threadpool de FastAPI -- así que dos visitantes concurrentes ya
# bastan para dispararlo. Serializar aquí, en el único punto que de
# verdad toca el estado global de Alembic, es más seguro y más simple
# que intentar coordinar el lock desde cada repositorio que lo llama.
_ALEMBIC_LOCK = threading.Lock()

# Auditoría Ronda 46, hallazgo #148 (costo de Alembic por llamada en
# importaciones de lote grandes -- corregido en la Ronda 51, y vuelto a
# corregir en la Ronda 54 tras un fallo real): cada repositorio de
# application/ llama a ensure_project_db() en CADA método (save/get/
# list...), no solo al abrir el proyecto una vez -- así que importar,
# por ejemplo, 25 fuentes en lote corre upgrade_project() (bajo el lock
# GLOBAL de Alembic, que serializa con TODA otra operación de cualquier
# proyecto en el proceso, no solo el que se está importando) decenas de
# veces, aunque el esquema ya esté al día desde la primera.
# `_ensured_project_dbs` recuerda, por proceso, qué archivos de base de
# datos ya se confirmaron -- para no repetir el upgrade completo en
# cada llamada subsiguiente sobre el mismo archivo.
#
# Ronda 54 -- fallo real encontrado por el consultor: la versión de la
# Ronda 51 guardaba solo la ruta resuelta como clave. RAG STUDIO es una
# aplicación de escritorio de proceso largo (no un servidor que se
# reinicia con cada despliegue) -- durante esta misma consultoría, el
# proceso de la aplicación real llevaba abierto desde antes de que se
# agregaran las migraciones 0017-0019, y ya había marcado el project.db
# de "AGENTE UDL" como "confirmado" en una revisión más vieja. Las
# migraciones nuevas nunca se aplicaron sobre ese archivo real mientras
# el proceso seguía corriendo -- exactamente el escenario que la Ronda
# 51 declaraba (de buena fe, pero equivocadamente) "no reachable hoy".
# Corrección: la clave de la caché ahora es (ruta_resuelta,
# revisión_head_actual_del_código) en vez de solo la ruta -- calcular la
# revisión head es una lectura ligera de los archivos de migración en
# disco (sin abrir ninguna conexión SQLite, sin tocar `_ALEMBIC_LOCK`),
# muchísimo más barata que el upgrade real, pero suficiente para que
# una migración nueva agregada AL CÓDIGO EN DISCO mientras el proceso
# sigue corriendo (el escenario real que falló) invalide la entrada
# vieja y fuerce una verificación real -- sin ese cambio, ningún
# reinicio de caché explícito (`forget_ensured_project_db`) hubiera
# bastado, porque nadie sabía que había que llamarlo.
_ensured_project_dbs: set[tuple[Path, str]] = set()
_ensured_project_dbs_lock = threading.Lock()


def _project_migrations_head() -> str:
    """Revisión `head` de las migraciones de proyecto, leída de los
    archivos en disco (ScriptDirectory.get_current_head()) -- no abre
    ninguna conexión SQLite ni toma `_ALEMBIC_LOCK`, así que es segura
    de llamar en cada ensure_project_db() sin pagar el costo real que
    la Ronda 51 quería evitar."""
    # Ronda 91 (auditoría de rendimiento con el proyecto real del
    # usuario): leer y compilar los ~20 scripts de migración costaba ~30
    # ms y se hacía en CADA llamada a ensure_project_db() -- 115 veces en
    # una sola simulación del Simulador (3.5 s de 7.5 s). Se conserva la
    # garantía de la Ronda 54 (una migración nueva agregada al código en
    # disco con el proceso abierto se detecta) usando como llave la firma
    # barata de la carpeta: fecha de modificación y nombre/fecha de cada
    # archivo .py (un os.scandir, sin abrir ni compilar nada).
    firma = _firma_carpeta_migraciones()
    with _head_cache_lock:
        if _head_cache.get("firma") == firma:
            return _head_cache["head"]
    head = ScriptDirectory(str(PROJECT_MIGRATIONS_DIR)).get_current_head()
    with _head_cache_lock:
        _head_cache["firma"] = firma
        _head_cache["head"] = head
    return head


_head_cache: dict = {}
_head_cache_lock = threading.Lock()


def _firma_carpeta_migraciones() -> tuple:
    versiones = PROJECT_MIGRATIONS_DIR / "versions"
    carpeta = versiones if versiones.is_dir() else PROJECT_MIGRATIONS_DIR
    with os.scandir(carpeta) as entradas:
        archivos = sorted(
            (e.name, e.stat().st_mtime_ns, e.stat().st_size) for e in entradas if e.name.endswith(".py")
        )
    return (carpeta.stat().st_mtime_ns, tuple(archivos))


def forget_ensured_project_db(db_path: str | Path) -> None:
    """Olvida que `db_path` ya se confirmó en `head`, para que la
    próxima llamada a `ensure_project_db()` vuelva a verificarlo de
    verdad. Pensado para un futuro comando que reemplace el contenido
    de un project.db ya abierto en este proceso (ver nota arriba) --
    ningún comando existente lo necesita hoy.

    La clave real de la caché incluye la revisión head (ver Ronda 54),
    que esta función no conoce -- descarta cualquier entrada de esa
    ruta sin importar con qué head se haya guardado."""
    resolved = Path(db_path).resolve()
    with _ensured_project_dbs_lock:
        _ensured_project_dbs.difference_update(
            {entry for entry in _ensured_project_dbs if entry[0] == resolved}
        )


def _find_repo_root(start: Path) -> Path:
    """Busca hacia arriba el directorio que contiene pyproject.toml.

    No asume una profundidad fija (por ejemplo, que este archivo viva
    bajo src/infrastructure/database/): funciona igual si el paquete
    está en un layout src/ o en un layout plano.
    """
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(
        f"No se encontró pyproject.toml subiendo desde {start}; "
        "no se puede ubicar la carpeta migrations/."
    )


def _resolve_migrations_root() -> Path:
    """Ubica la carpeta `migrations/` tanto en desarrollo (subiendo
    desde este archivo hasta encontrar `pyproject.toml`, comportamiento
    de siempre) como empaquetado con PyInstaller (ítem 7 de la segunda
    evaluación de madurez post-8-etapas, ver bitácora): un ejecutable
    congelado con PyInstaller no tiene `pyproject.toml` en disco ni
    `Path(__file__)` apuntando al árbol fuente real, así que
    `_find_repo_root` nunca lo encontraría -- `sys._MEIPASS` es el
    directorio temporal donde PyInstaller extrae los archivos de datos
    incluidos (ver `packaging/ragstudio.spec`, que agrega `migrations/`
    ahí explícitamente), y es el único lugar donde hay que buscar
    cuando existe."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base is not None:
        frozen_migrations = Path(frozen_base) / "migrations"
        if frozen_migrations.exists():
            return frozen_migrations
    return _find_repo_root(Path(__file__).resolve()) / "migrations"


_MIGRATIONS_ROOT = _resolve_migrations_root()
GLOBAL_MIGRATIONS_DIR = _MIGRATIONS_ROOT / "global"
PROJECT_MIGRATIONS_DIR = _MIGRATIONS_ROOT / "project"


def _config_for(script_location: Path, db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(script_location))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def upgrade_global(db_path: str | Path, revision: str = "head") -> None:
    with _ALEMBIC_LOCK:
        command.upgrade(_config_for(GLOBAL_MIGRATIONS_DIR, Path(db_path)), revision)


def downgrade_global(db_path: str | Path, revision: str = "base") -> None:
    with _ALEMBIC_LOCK:
        command.downgrade(_config_for(GLOBAL_MIGRATIONS_DIR, Path(db_path)), revision)


def upgrade_project(db_path: str | Path, revision: str = "head") -> None:
    with _ALEMBIC_LOCK:
        command.upgrade(_config_for(PROJECT_MIGRATIONS_DIR, Path(db_path)), revision)


def downgrade_project(db_path: str | Path, revision: str = "base") -> None:
    with _ALEMBIC_LOCK:
        command.downgrade(_config_for(PROJECT_MIGRATIONS_DIR, Path(db_path)), revision)


def ensure_project_db(paths, project_id: str) -> Path:
    """Garantiza que el project.db de `project_id` exista en disco y
    esté en la revisión más reciente (head) de las migraciones de
    proyecto.

    A diferencia de solo llamar a upgrade_project() cuando el archivo
    todavía no existe (patrón usado originalmente en cada repositorio
    -- ver bitácora del README), esto corre upgrade_project() la
    primera vez que se abre cada project.db en la vida de este proceso
    PARA UNA REVISIÓN HEAD DADA (ver más abajo). Alembic ya es
    idempotente: guarda la revisión aplicada en su propia tabla
    `alembic_version` dentro del mismo project.db y en cada llamada
    solo aplica las migraciones pendientes (0 si ya está al día) --
    pero esa comprobación (crear el engine, leer `alembic_version`,
    comparar contra `head`) tiene un costo real que se paga en cada
    apertura del proyecto, bajo un lock global que serializa con
    cualquier otra operación de Alembic del proceso entero
    (`_ALEMBIC_LOCK`). Auditoría Ronda 46, hallazgo #148 (corregido en
    la Ronda 51, y corregido de nuevo en la Ronda 54 -- ver abajo): como
    cada repositorio llama a esto en CADA método, no solo al abrir el
    proyecto, importar un lote grande de fuentes pagaba ese costo
    decenas de veces por nada -- `_ensured_project_dbs` recuerda qué
    archivos ya se confirmaron para no repetir la verificación completa
    en cada llamada subsiguiente sobre el mismo archivo.

    Ronda 54 -- la caché ahora se indexa por (ruta_resuelta,
    head_actual_del_código), no solo por ruta: la versión de la Ronda
    51 fallaba de verdad en el escenario real de una aplicación de
    escritorio de proceso largo -- si el proceso ya llevaba abierto (y
    ya había marcado un project.db como "confirmado") desde ANTES de
    que se agregara una migración nueva al código en disco, esa
    migración nunca se aplicaba mientras el proceso seguía corriendo,
    aunque el propio código ya la conociera. `_project_migrations_head()`
    relee los archivos de migración en cada llamada (barato, sin tocar
    SQLite ni `_ALEMBIC_LOCK`) -- si el head cambió desde la última
    confirmación de esta misma ruta, la entrada vieja ya no coincide y
    se vuelve a verificar de verdad contra la base de datos real.

    Sin esto, un proyecto creado con una versión anterior del código
    (antes de que existiera una migración nueva, p. ej.
    0004_index_info) se queda "atascado" para siempre en su esquema
    viejo: su project.db ya existe en disco, así que el chequeo
    "if not db_path.exists()" nunca se cumple de nuevo y la migración
    nueva no se aplica aunque el código ya la conozca. Esto es lo que
    producía `sqlite3.OperationalError: no such table: index_info` al
    abrir un proyecto creado antes de la Etapa 4 con el código de la
    Etapa 4 ya instalado -- y, de una forma más sutil (proceso largo en
    vez de proyecto viejo), lo que producía
    `sqlite3.OperationalError: no such column: project.quality_regression_threshold`
    reportado por el consultor en la Ronda 54.
    """
    paths.ensure_project_layout(project_id)
    db_path = paths.project_db_path(project_id)
    resolved = db_path.resolve()
    cache_key = (resolved, _project_migrations_head())
    with _ensured_project_dbs_lock:
        already_ensured = cache_key in _ensured_project_dbs
    if already_ensured:
        return db_path
    upgrade_project(db_path)
    with _ensured_project_dbs_lock:
        _ensured_project_dbs.add(cache_key)
    return db_path
