from __future__ import annotations

from domain.conversational.entities import GuardrailRule
from domain.conversational.ports import GuardrailRuleRepository


class ListGuardrailRules:
    def __init__(self, repository: GuardrailRuleRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[GuardrailRule]:
        return self._repository.list_for_project(project_id)
