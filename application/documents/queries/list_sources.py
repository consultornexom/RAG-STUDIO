from __future__ import annotations

from domain.documents.entities import Source
from domain.documents.ports import SourceRepository


class ListSources:
    def __init__(self, repository: SourceRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[Source]:
        return self._repository.list_for_project(project_id)
