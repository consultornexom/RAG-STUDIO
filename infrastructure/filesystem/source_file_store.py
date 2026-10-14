"""Implementación filesystem de SourceFileStore (domain.documents.ports),
sobre el layout ya reservado en InstallationPaths
(`sources/original/` dentro de cada proyecto)."""
from __future__ import annotations

import shutil
from pathlib import Path

from domain.documents.ports import SourceFileStore

from .paths import InstallationPaths


class FilesystemSourceFileStore(SourceFileStore):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _original_dir(self, project_id: str) -> Path:
        # ensure_project_layout ya crea sources/original/ (ver
        # infrastructure/filesystem/paths.py), pero se vuelve a
        # garantizar aquí por si esta implementación se usa alguna vez
        # sin haber pasado antes por ensure_project_layout.
        directory = self._paths.project_dir(project_id) / "sources" / "original"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def store_original(self, project_id: str, source_id: str, external_path: str) -> str:
        source_path = Path(external_path)
        # shutil.copy2 ya lanza FileNotFoundError/IsADirectoryError/
        # PermissionError (subclases de OSError) tal cual si
        # external_path no es un archivo legible -- se deja propagar
        # sin envolver, quien llama en application decide qué hacer.
        destination = self._original_dir(project_id) / f"{source_id}{source_path.suffix}"
        shutil.copy2(source_path, destination)
        return str(destination)
