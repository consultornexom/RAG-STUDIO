from __future__ import annotations

from typing import Optional

from domain.conversational.entities import Intent, IntentResolutionMode, IntentRiskLevel
from domain.conversational.ports import IntentRepository


class CreateIntent:
    def __init__(self, repository: IntentRepository):
        self._repository = repository

    def execute(
        self, project_id: str, name: str, description: str = "",
        positive_examples: Optional[list[str]] = None, negative_examples: Optional[list[str]] = None,
        priority: int = 0, risk_level: IntentRiskLevel = IntentRiskLevel.BAJO,
        required_variables: Optional[list[str]] = None, optional_variables: Optional[list[str]] = None,
        clarifying_questions: Optional[dict[str, str]] = None, response_rule: str = "",
        fallback_channeling_code: Optional[str] = None,
        resolution_mode: IntentResolutionMode = IntentResolutionMode.SEMANTICO,
    ) -> Intent:
        intent = Intent(
            project_id=project_id, name=name, description=description,
            positive_examples=list(positive_examples or []), negative_examples=list(negative_examples or []),
            priority=priority, risk_level=risk_level,
            required_variables=list(required_variables or []), optional_variables=list(optional_variables or []),
            clarifying_questions=dict(clarifying_questions or {}), response_rule=response_rule,
            fallback_channeling_code=fallback_channeling_code, resolution_mode=resolution_mode,
        )
        self._repository.save(intent)
        return intent
