from __future__ import annotations

from domain.conversational.entities import ConversationalVariable
from domain.conversational.ports import ConversationalVariableRepository


class ListConversationalVariables:
    def __init__(self, repository: ConversationalVariableRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[ConversationalVariable]:
        return self._repository.list_for_project(project_id)
