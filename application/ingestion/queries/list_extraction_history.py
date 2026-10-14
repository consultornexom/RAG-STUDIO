"""Caso de uso: consultar el historial de auditoría de extracciones de
una fuente (ítem 5 de la evaluación de madurez post-8-etapas)."""
from __future__ import annotations

from domain.ingestion.entities import ExtractionRecord
from domain.ingestion.ports import ExtractionRepository


class ListExtractionHistory:
    def __init__(self, repository: ExtractionRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> list[ExtractionRecord]:
        return self._repository.list_history(project_id, source_id)
