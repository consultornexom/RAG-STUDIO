from __future__ import annotations

from typing import Optional

from domain.ingestion.entities import ExtractionRecord
from domain.ingestion.ports import ExtractionRepository


class GetExtractionRecord:
    def __init__(self, repository: ExtractionRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> Optional[ExtractionRecord]:
        return self._repository.get(project_id, source_id)
