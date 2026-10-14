from __future__ import annotations

from datetime import datetime, timezone

from domain.conversational.entities import GuardrailRule
from domain.conversational.exceptions import GuardrailRuleNotFoundError
from domain.conversational.ports import GuardrailRuleRepository


class SetGuardrailRuleActive:
    def __init__(self, repository: GuardrailRuleRepository):
        self._repository = repository

    def execute(self, project_id: str, rule_id: str, active: bool) -> GuardrailRule:
        rule = self._repository.get(project_id, rule_id)
        if rule is None:
            raise GuardrailRuleNotFoundError(project_id, rule_id)
        updated = rule.model_copy(update={"active": active, "updated_at": datetime.now(timezone.utc)})
        self._repository.save(updated)
        return updated
