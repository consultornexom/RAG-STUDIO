"""SHA-256 de la copia del original de una fuente (RAG-INC-01, relleno de
content_hash; decisión NEXOM sobre INC01-R1).

Solo lee `<proyecto>/sources/original/<source_id>.<ext>` (la copia que
FilesystemSourceFileStore guarda como `<source_id><sufijo>`). Nunca lee
`location`. Mismo formato que el alta actual (ui/sources/panel.py y
register_sources_from_folder): hex en minúsculas de los bytes exactos.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from domain.documents.entities import Source
from domain.documents.exceptions import OriginalCopyMissingError, OriginalCopyUnreadableError
from domain.documents.manifest import extraer_nombre_base_multiplataforma
from domain.documents.ports import SourceOriginalHasher

from .paths import InstallationPaths

_BLOQUE = 1024 * 1024


class FilesystemSourceOriginalHasher(SourceOriginalHasher):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _copia(self, project_id: str, source: Source) -> Path:
        carpeta = self._paths.project_dir(project_id) / "sources" / "original"
        if not carpeta.is_dir():
            raise OriginalCopyMissingError(source.id, "La carpeta sources/original/ no existe.")
        candidatas = sorted(
            p for p in carpeta.iterdir()
            if p.name == source.id or p.name.startswith(source.id + ".")
        )
        if not candidatas:
            raise OriginalCopyMissingError(source.id)
        if len(candidatas) == 1:
            return candidatas[0]
        # Varias copias con el mismo id (p. ej. se corrigió la ubicación antes
        # de extraer y cambió la extensión): solo vale la que registra la base.
        registrada = extraer_nombre_base_multiplataforma(source.original_copy_path or "")
        elegidas = [p for p in candidatas if p.name == registrada]
        if len(elegidas) == 1:
            return elegidas[0]
        raise OriginalCopyUnreadableError(
            source.id, "hay varias copias candidatas y ninguna coincide con original_copy_path: "
            + ", ".join(p.name for p in candidatas),
        )

    def sha256_of_original(self, project_id: str, source: Source) -> str:
        copia = self._copia(project_id, source)
        if not copia.is_file():
            raise OriginalCopyUnreadableError(source.id, f"{copia.name} no es un archivo regular")
        digest = hashlib.sha256()
        try:
            with open(copia, "rb") as handle:
                for bloque in iter(lambda: handle.read(_BLOQUE), b""):
                    digest.update(bloque)
        except OSError as exc:
            raise OriginalCopyUnreadableError(source.id, f"{copia.name}: {exc}") from exc
        return digest.hexdigest()
