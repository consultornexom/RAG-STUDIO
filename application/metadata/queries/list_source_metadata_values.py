from __future__ import annotations

from domain.metadata.entities import SourceMetadataValue
from domain.metadata.ports import SourceMetadataRepository


class ListSourceMetadataValues:
    def __init__(self, repository: SourceMetadataRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> list[SourceMetadataValue]:
        return self._repository.list_values_for_source(project_id, source_id)
