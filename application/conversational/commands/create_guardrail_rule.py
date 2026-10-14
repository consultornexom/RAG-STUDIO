from __future__ import annotations

from typing import Optional, Sequence, Union

from domain.conversational.entities import GuardrailRule, RuleActionType, RuleCondition, RuleType
from domain.conversational.ports import GuardrailRuleRepository


class CreateGuardrailRule:
    def __init__(self, repository: GuardrailRuleRepository):
        self._repository = repository

    def execute(
        self, project_id: str, name: str, rule_type: RuleType,
        # Sequence (covariante) en vez de list (invariante): este método
        # solo LEE `conditions` para construir una lista nueva, nunca lo
        # modifica -- así una llamada con list[RuleCondition] (más
        # específico que list[RuleCondition | dict]) sigue siendo
        # aceptada sin perder seguridad de tipos real.
        conditions: Optional[Sequence[Union[RuleCondition, dict]]] = None,
        action: RuleActionType = RuleActionType.RESPONDER, priority: int = 0,
    ) -> GuardrailRule:
        # Cada condición puede llegar ya como RuleCondition (llamadas
        # internas/pruebas) o como dict {"field", "operator", "value"}
        # (la UI, que nunca importa domain -- ver
        # ui.conversational.parsing.parse_conditions, ADR-001 sección 4).
        parsed_conditions = [
            condition if isinstance(condition, RuleCondition) else RuleCondition(**condition)
            for condition in (conditions or [])
        ]
        rule = GuardrailRule(
            project_id=project_id, name=name, rule_type=rule_type,
            conditions=parsed_conditions, action=action, priority=priority,
        )
        self._repository.save(rule)
        return rule
