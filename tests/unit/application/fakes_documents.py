"""Dobles de prueba en memoria para el contexto Documentos."""
from __future__ import annotations

from typing import Optional

from domain.documents.entities import Source
from domain.documents.ports import SourceFileStore, SourceRepository


class InMemorySourceRepository(SourceRepository):
    def __init__(self):
        self._by_id: dict[str, Source] = {}

    def save(self, source: Source) -> None:
        self._by_id[source.id] = source

    def get(self, project_id: str, source_id: str) -> Optional[Source]:
        source = self._by_id.get(source_id)
        return source if source and source.project_id == project_id else None

    def get_by_content_hash(self, project_id: str, content_hash: str) -> Optional[Source]:
        return next(
            (s for s in self._by_id.values() if s.project_id == project_id and s.content_hash == content_hash),
            None,
        )

    def list_for_project(self, project_id: str) -> list[Source]:
        return [s for s in self._by_id.values() if s.project_id == project_id]


class InMemorySourceFileStore(SourceFileStore):
    """Doble en memoria de SourceFileStore (ítem 4 de la evaluación de
    madurez post-8-etapas) -- no toca el sistema de archivos real. Cada
    llamada queda registrada en `calls` para poder afirmar que
    RegisterSource/UpdateSourceDetails la invocan (o no) según el caso.
    `missing_paths` simula rutas externas no legibles en ese momento,
    para probar que un fallo de copia no tumba el registro/edición (ver
    RegisterSource._try_copy_original)."""

    def __init__(self, missing_paths: Optional[set[str]] = None):
        self.calls: list[tuple[str, str, str]] = []
        self._missing_paths = missing_paths or set()

    def store_original(self, project_id: str, source_id: str, external_path: str) -> str:
        self.calls.append((project_id, source_id, external_path))
        if external_path in self._missing_paths:
            raise FileNotFoundError(external_path)
        return f"/fake-store/{project_id}/sources/original/{source_id}"
