"""Implementación filesystem de ProjectSnapshotPublisher
(domain.release.ports) -- ADR-002, Fase 1.

Antes de copiar, fuerza un checkpoint del WAL de SQLite
(`PRAGMA wal_checkpoint(TRUNCATE)`) para que `project.db` quede
autocontenido: project.db está en modo WAL (ver
infrastructure/database/engine.py) para tolerar accesos concurrentes
de la UI y los jobs en segundo plano; sin el checkpoint, copiar solo
project.db sin sus archivos -wal/-shm podría dejar una instantánea con
escrituras confirmadas pero no aplicadas todavía al archivo principal.

Queda una ventana teórica pequeña si ocurre una escritura real entre
el checkpoint y la copia -- mismo perfil de riesgo que ya acepta hoy
FilesystemProjectPackager (ExportProject/BackupProject) al copiar
project_dir de forma recursiva sin coordinarse con Qdrant ni con
SQLite. No se resuelve aquí (pausar toda la actividad de la app
durante la publicación es una decisión de producto fuera de alcance
de esta fase, ver ADR-002 sección 5).

Ronda 92: al terminar la copia escribe `snapshot_identity.json` dentro
de la instantánea (proyecto, versión, modelo de embeddings y huella de
contenido portable) -- ver infrastructure/filesystem/snapshot_identity.py.
Así la carpeta se describe sola y el runtime ya no depende de que el
operador adivine la versión."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from domain.release.ports import ProjectSnapshotPublisher
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.snapshot_identity import build_snapshot_identity, write_snapshot_identity


class FilesystemProjectSnapshotPublisher(ProjectSnapshotPublisher):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def publish(self, project_id: str, version: int) -> str:
        project_dir = self._paths.project_dir(project_id)
        self._checkpoint_wal(self._paths.project_db_path(project_id))

        destination = self._paths.snapshot_version_dir(project_id, version)
        if destination.exists():
            raise FileExistsError(f"Ya existe una instantánea publicada en {destination}.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        shutil.copytree(project_dir, destination)
        try:
            write_snapshot_identity(destination, build_snapshot_identity(
                destination, project_id, version, published_at=datetime.now(timezone.utc),
            ))
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return str(destination)

    @staticmethod
    def _checkpoint_wal(db_path: Path) -> None:
        if not db_path.exists():
            return
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            connection.commit()
        finally:
            connection.close()
