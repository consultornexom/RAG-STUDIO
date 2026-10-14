from __future__ import annotations

from domain.documents.entities import Source
from domain.documents.exceptions import SourceNotFoundError
from domain.documents.ports import SourceRepository


class GetSource:
    def __init__(self, repository: SourceRepository):
        self._repository = repository

    def execute(self, project_id: str, source_id: str) -> Source:
        source = self._repository.get(project_id, source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source
