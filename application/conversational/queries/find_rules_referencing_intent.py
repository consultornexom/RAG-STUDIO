"""Consulta: ¿qué reglas de guardrail referencian el nombre de una
intención como texto libre en una condición?

Hallazgo de la Ronda 4 de Validacion_observaciones_RAG_STUDIO.md
(re-análisis posterior a agregar UpdateIntent, mejora 5 de la Ronda 3):
domain.conversational.rule_evaluation evalúa condiciones contra un
contexto donde "intencion" es el NOMBRE de la intención emparejada
(ver application.conversational.queries.simulate_conversation,
context["intencion"] = intent.name) -- nunca su id. Antes de que
existiera UpdateIntent esto no era un riesgo porque el nombre de una
intención era inmutable; ahora que se puede corregir, una regla con una
condición como `intencion = "Consultar Requisitos"` deja de cumplirse
en silencio si esa intención se renombra, sin ningún error ni aviso
(evaluate_condition simplemente devuelve False para un valor que ya no
coincide).

Esta consulta no bloquea el renombrado (una condición de texto libre
puede coincidir con muchas cosas a propósito; bloquear sería
demasiado agresivo) -- se usa para avisar explícitamente al usuario
qué reglas hay que revisar, siguiendo el mismo criterio ya aplicado a
los valores de metadatos huérfanos (avisar en vez de fallar en
silencio u ocultar el problema)."""
from __future__ import annotations

from domain.conversational.entities import GuardrailRule
from domain.conversational.ports import GuardrailRuleRepository
from domain.conversational.text_normalization import normalize_text

INTENT_NAME_CONDITION_FIELD = "intencion"


def _matches_intent_name(value: str, intent_name: str) -> bool:
    # Misma normalización que domain.conversational.rule_evaluation.
    # _coerce_pair para el caso de texto (minúsculas, sin espacios en
    # los extremos) -- si no se usara la misma regla aquí, esta
    # consulta podría no avisar sobre una condición que en la práctica
    # sí iba a dejar de cumplirse (o avisar de una que nunca aplicaba).
    # Ronda 87: sin acentos también, igual que la evaluación real.
    return normalize_text(value) == normalize_text(intent_name)


class FindRulesReferencingIntent:
    def __init__(self, guardrail_repository: GuardrailRuleRepository):
        self._guardrail_repository = guardrail_repository

    def execute(self, project_id: str, intent_name: str) -> list[GuardrailRule]:
        if not intent_name.strip():
            return []
        rules = self._guardrail_repository.list_for_project(project_id)
        return [
            rule for rule in rules
            if any(
                condition.field == INTENT_NAME_CONDITION_FIELD
                and _matches_intent_name(condition.value, intent_name)
                for condition in rule.conditions
            )
        ]
