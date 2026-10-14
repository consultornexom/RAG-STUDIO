from __future__ import annotations

from domain.ingestion.entities import Chunk
from domain.ingestion.ports import ChunkRepository


class ListChunks:
    def __init__(self, repository: ChunkRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> list[Chunk]:
        return self._repository.list_for_source(project_id, source_id)
