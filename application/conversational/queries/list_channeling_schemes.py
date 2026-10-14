from __future__ import annotations

from domain.conversational.entities import ChannelingScheme
from domain.conversational.ports import ChannelingSchemeRepository


class ListChannelingSchemes:
    def __init__(self, repository: ChannelingSchemeRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[ChannelingScheme]:
        return self._repository.list_for_project(project_id)
