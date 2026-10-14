from __future__ import annotations

from domain.conversational.entities import Intent
from domain.conversational.ports import IntentRepository


class ListIntents:
    def __init__(self, repository: IntentRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[Intent]:
        return self._repository.list_for_project(project_id)
