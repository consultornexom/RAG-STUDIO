"""Caso de uso: editar una regla de guardrail (Ronda 3, punto 13 --
solo el nombre; ampliado en el ajuste funcional del 2026-09-03,
hallazgo real de usuario, ver bitácora).

Antes de este ajuste, `rule_type`, `conditions`, `action` y `priority`
quedaban deliberadamente fuera de la edición -- "son la lógica real de
la regla, no solo su identificación", con el criterio documentado de
"crear una regla nueva y desactivar la anterior" para cambiarlos (ver
Manual del Usuario, sección de Guardrails). El usuario reportó que esa
vía documentada tampoco existía en la interfaz (no había ningún botón
"Eliminar"), así que quedó atrapado sin ninguna forma de corregir una
regla mal configurada salvo desactivarla y dejar una regla "muerta" en
el proyecto. Se resuelve con dos cambios complementarios: aquí, edición
completa (mismo criterio ya usado por UpdateChannelingScheme -- todos
los campos opcionales, solo se sobrescribe lo que se pasa
explícitamente); y en delete_guardrail_rule.py, la opción de eliminar
que el manual siempre asumió que existía."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from domain.conversational.entities import GuardrailRule, RuleActionType, RuleCondition, RuleType
from domain.conversational.exceptions import GuardrailRuleNotFoundError
from domain.conversational.ports import GuardrailRuleRepository


class UpdateGuardrailRule:
    def __init__(self, repository: GuardrailRuleRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        rule_id: str,
        name: str,
        rule_type: Optional[RuleType] = None,
        conditions: Optional[Sequence[Union[RuleCondition, dict]]] = None,
        action: Optional[RuleActionType] = None,
        priority: Optional[int] = None,
    ) -> GuardrailRule:
        rule = self._repository.get(project_id, rule_id)
        if rule is None:
            raise GuardrailRuleNotFoundError(project_id, rule_id)

        update: dict = {"name": name, "updated_at": datetime.now(timezone.utc)}
        if rule_type is not None:
            # model_copy(update=...) NUNCA valida/coacciona -- a
            # diferencia del constructor de GuardrailRule (usado por
            # CreateGuardrailRule), asignar aquí un string plano tal
            # cual (p. ej. QComboBox.currentText()) dejaría
            # rule.rule_type como str en vez de RuleType, rompiendo
            # SqlAlchemyGuardrailRuleRepository.save (usa .value). Se
            # coacciona explícitamente antes de asignar, mismo criterio
            # que UpdateIntent con resolution_mode.
            update["rule_type"] = RuleType(rule_type)
        if conditions is not None:
            # Cada condición puede llegar ya como RuleCondition o como
            # dict {"field", "operator", "value"} (la UI, que nunca
            # importa domain -- ver ui.conversational.parsing.
            # parse_conditions) -- mismo criterio que CreateGuardrailRule.
            update["conditions"] = [
                condition if isinstance(condition, RuleCondition) else RuleCondition(**condition)
                for condition in conditions
            ]
        if action is not None:
            update["action"] = RuleActionType(action)
        if priority is not None:
            update["priority"] = priority

        updated = rule.model_copy(update=update)
        self._repository.save(updated)
        return updated
