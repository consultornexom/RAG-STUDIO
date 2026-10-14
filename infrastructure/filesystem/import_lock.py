"""Bloqueo entre procesos para la importación de proyectos (RAG-INC-01a,
Alcance firmado, INC01-R9).

Mecanismo: bloqueo **exclusivo del sistema operativo** sobre el archivo
``<instalación>/.importacion.lock``:

- POSIX (Linux, macOS): ``fcntl.flock(fd, LOCK_EX | LOCK_NB)``. El bloqueo
  pertenece a la descripción de archivo abierta, así que también excluye a
  otro hilo del mismo proceso que abra el archivo por su cuenta.
- Windows: ``msvcrt.locking(fd, LK_NBLCK, 1)`` sobre el primer byte.

El sistema operativo libera el bloqueo al cerrar el descriptor o al terminar
el proceso, incluso si muere abruptamente: nunca queda una instalación
"bloqueada para siempre". La existencia del archivo NO significa nada (no es
un archivo centinela); solo importa quién tiene el bloqueo.

La espera tiene un tiempo máximo. Al agotarse se lanza
ImportLockTimeoutError sin haber modificado nada.
"""
from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from domain.projects.exceptions import ImportLockTimeoutError
from domain.projects.ports import ImportLock

LOCK_FILENAME = ".importacion.lock"


def _intentar(fd: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover - no se ejecuta en CI Linux
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, PermissionError):
        return False


def _soltar(fd: int) -> None:
    if sys.platform == "win32":  # pragma: no cover
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


class FileImportLock(ImportLock):
    def __init__(self, base_dir: str | Path, timeout_s: float = 30.0, intervalo_s: float = 0.05):
        self._ruta = Path(base_dir) / LOCK_FILENAME
        self._timeout_s = timeout_s
        self._intervalo_s = intervalo_s

    @property
    def path(self) -> Path:
        return self._ruta

    @contextmanager
    def hold(self) -> Iterator[None]:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._ruta, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            limite = time.monotonic() + self._timeout_s
            while not _intentar(fd):
                if time.monotonic() >= limite:
                    raise ImportLockTimeoutError(self._timeout_s)
                time.sleep(self._intervalo_s)
            try:
                yield
            finally:
                _soltar(fd)
        finally:
            os.close(fd)
