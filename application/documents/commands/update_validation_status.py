"""Caso de uso: mover el estado de validación de una fuente."""
from __future__ import annotations

from domain.documents.entities import Source, SourceValidationStatus
from domain.documents.exceptions import SourceNotFoundError
from domain.documents.ports import SourceRepository


class UpdateSourceValidationStatus:
    def __init__(self, repository: SourceRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str, target_status: SourceValidationStatus) -> Source:
        source = self._repository.get(project_id, source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        updated = source.transition_validation_to(target_status)
        self._repository.save(updated)
        return updated
