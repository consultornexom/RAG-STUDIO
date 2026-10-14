"""Caso de uso: consultar el historial de auditoría de cambios de un
campo de metadatos para una fuente (ítem 5 de la evaluación de
madurez post-8-etapas)."""
from __future__ import annotations

from typing import Optional

from domain.metadata.entities import MetadataValueChange
from domain.metadata.ports import SourceMetadataRepository


class ListMetadataValueHistory:
    def __init__(self, repository: SourceMetadataRepository):
        self._repository = repository

    def execute(
        self, project_id: str, source_id: str, field_id: Optional[str] = None,
    ) -> list[MetadataValueChange]:
        return self._repository.list_value_history(project_id, source_id, field_id)
