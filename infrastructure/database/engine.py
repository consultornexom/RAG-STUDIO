"""Fábrica de engines y sesiones de SQLAlchemy para SQLite global/por proyecto."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Tiempo máximo (en milisegundos) que una conexión espera un lock antes de
# lanzar "database is locked". Ítem 1 de la segunda evaluación de madurez
# post-8-etapas (ver bitácora): esta app abre la misma base SQLite desde
# varios hilos a la vez (UI + ThreadJobRunner), y con el modo de
# journaling por defecto (rollback journal) más el timeout por defecto de
# sqlite3 (5s) eso puede producir bloqueos reales bajo escritura
# concurrente, no solo en teoría.
_DEFAULT_BUSY_TIMEOUT_MS = 30_000


def make_sqlite_engine(db_path: str | Path, *, busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: los trabajos en segundo plano (workers) usan
    # su propia conexión/sesión de corta vida; nunca comparten una sesión
    # abierta entre hilos. timeout=busy_timeout_ms/1000 es el equivalente
    # de sqlite3 a nivel de driver Python (además del PRAGMA busy_timeout
    # de abajo, que es el equivalente a nivel del motor SQLite).
    engine = create_engine(
        f"sqlite:///{db_path}", future=True,
        connect_args={"check_same_thread": False, "timeout": busy_timeout_ms / 1000},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        try:
            # WAL: los lectores no bloquean al escritor ni viceversa (a
            # diferencia del rollback journal por defecto) -- es exactamente
            # el escenario de esta app: la UI puede estar leyendo mientras
            # un job en segundo plano escribe. Queda grabado en el archivo
            # .db (no hay que repetirlo en cada conexión, pero repetirlo es
            # barato e inofensivo si ya está en WAL).
            #
            # Nota (auditoría de madurez ronda 5, solo documentación --
            # no requiere ningún cambio de código hoy): el modo WAL de
            # SQLite no es confiable sobre unidades de red (SMB/NFS,
            # incluyendo unidades "de red" mapeadas como letra en
            # Windows), porque necesita locks de archivo compartido que
            # esos protocolos no siempre implementan bien -- puede
            # corromper la base. Esta app siempre guarda su base de
            # datos dentro del propio directorio de instalación (ver
            # ítem "Cambiar ubicación por defecto de los datos" en la
            # bitácora), así que hoy esto no aplica -- pero si en algún
            # momento se permitiera reubicar los datos, esa ubicación no
            # debe ser una unidad de red.
            cursor.execute("PRAGMA journal_mode=WAL")
            # Si de todos modos hay contención momentánea (dos escrituras
            # verdaderamente simultáneas), reintentar en silencio hasta
            # busy_timeout_ms en vez de fallar de inmediato.
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        finally:
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
