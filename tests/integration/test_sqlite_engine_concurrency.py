"""Pruebas de integración reales (SQLite en disco) del ítem 1 de la
segunda evaluación de madurez post-8-etapas: modo WAL + busy_timeout en
`infrastructure.database.engine.make_sqlite_engine`.

Antes, la base SQLite (global o por proyecto) se abría con el modo de
journaling por defecto (rollback journal) y sin busy_timeout explícito.
Esta app abre la misma base desde varios hilos a la vez (la UI y
`workers.jobs.ThreadJobRunner`), así que una escritura concurrente real
podía producir `OperationalError: database is locked` en vez de
esperar y reintentar. Estas pruebas confirman, contra archivos .db
reales (no dobles), que:

1. El modo WAL queda activo tras conectar.
2. `PRAGMA busy_timeout` queda configurado con el valor pedido.
3. Varios hilos escribiendo de verdad al mismo archivo, cada uno con su
   propio engine/conexión (como hace la app real: cada operación de
   repositorio abre su propio engine de corta vida), no lanzan
   "database is locked" -- se serializan esperando el lock en vez de
   fallar de inmediato.
"""
from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import text

from infrastructure.database.engine import make_sqlite_engine


def test_wal_mode_is_enabled_on_connect(tmp_path: Path):
    engine = make_sqlite_engine(tmp_path / "wal_test.db")
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode is not None
    assert mode.lower() == "wal"


def test_busy_timeout_is_configured(tmp_path: Path):
    engine = make_sqlite_engine(tmp_path / "timeout_test.db", busy_timeout_ms=12_345)
    with engine.connect() as conn:
        timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert timeout == 12_345


def test_default_busy_timeout_is_generous_enough_for_background_jobs(tmp_path: Path):
    engine = make_sqlite_engine(tmp_path / "default_timeout_test.db")
    with engine.connect() as conn:
        timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
    # 30s por defecto: generoso para un job en segundo plano (fragmentar,
    # indexar) que escribe mientras la UI hace una lectura corta.
    assert timeout == 30_000


def test_concurrent_writes_from_multiple_threads_do_not_raise_database_locked(tmp_path: Path):
    db_path = tmp_path / "concurrent_test.db"
    setup_engine = make_sqlite_engine(db_path)
    with setup_engine.begin() as conn:
        conn.execute(text("CREATE TABLE counter (thread_id INTEGER, n INTEGER)"))

    errors: list[BaseException] = []
    writes_per_thread = 25
    thread_count = 6

    def _write_many(thread_id: int) -> None:
        try:
            # Cada hilo abre su propio engine, igual que hace cada
            # operación de repositorio real en esta app (no comparten
            # una sesión entre hilos).
            engine = make_sqlite_engine(db_path)
            for n in range(writes_per_thread):
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO counter (thread_id, n) VALUES (:tid, :n)"),
                        {"tid": thread_id, "n": n},
                    )
        except BaseException as exc:  # noqa: BLE001 - queremos capturar cualquier fallo del hilo
            errors.append(exc)

    threads = [threading.Thread(target=_write_many, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"Escrituras concurrentes fallaron: {errors!r}"

    verify_engine = make_sqlite_engine(db_path)
    with verify_engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM counter")).scalar()
    assert total == thread_count * writes_per_thread
