"""Caso de uso: eliminar una regla de guardrail (ajuste funcional del
2026-09-03, hallazgo real de usuario -- ver bitácora).

El Manual del Usuario ya documentaba "eliminar y crear nuevamente"
como la vía para cambiar tipo, condiciones, acción o prioridad de una
regla (ver update_guardrail_rule.py, que deliberadamente no toca esos
campos), pero la interfaz nunca ofreció ningún botón "Eliminar" -- el
usuario reportó tener que desactivar la regla en su lugar, como
solución temporal, porque el manual no coincidía con lo que la
interfaz permitía hacer.

Sin chequeo de "en uso" (a diferencia de DeleteFieldDefinition o
DeleteTestCase): ver domain.conversational.ports.
GuardrailRuleRepository.delete -- ninguna otra entidad de este
dominio referencia una GuardrailRule por id."""
from __future__ import annotations

from domain.conversational.exceptions import GuardrailRuleNotFoundError
from domain.conversational.ports import GuardrailRuleRepository


class DeleteGuardrailRule:
    def __init__(self, repository: GuardrailRuleRepository):
        self._repository = repository

    def execute(self, project_id: str, rule_id: str) -> None:
        rule = self._repository.get(project_id, rule_id)
        if rule is None:
            raise GuardrailRuleNotFoundError(project_id, rule_id)
        self._repository.delete(project_id, rule_id)
