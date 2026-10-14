"""Caso de uso: editar una intención (Ronda 3, punto 13 de
Validacion_observaciones_RAG_STUDIO.md, más resolution_mode -- Pista
B.4 del ADR-003; ampliado a la ficha completa en el ajuste funcional
del 2026-09-03, hallazgo real de usuario, ver bitácora).

Antes de este ajuste, solo se podían corregir nombre, descripción y
resolution_mode -- el resto de la configuración (ejemplos positivos y
negativos, prioridad, nivel de riesgo, datos mínimos y opcionales,
preguntas aclaratorias, regla de respuesta, canalización alternativa)
quedaba bloqueado desde la interfaz, obligando a desactivar la
intención y crear otra nueva para cualquier ajuste que no fuera de
nombre o descripción -- exactamente el mismo problema, con el mismo
usuario, que llevó a UpdateGuardrailRule a ganar edición completa en
esta misma ronda.

`id` y `project_id` nunca son editables (identidad de la intención);
`active`/`created_at` tampoco se tocan aquí (ver SetIntentActive). El
resto de los campos son opcionales -- solo se sobrescribe lo que se
pasa explícitamente, mismo criterio que UpdateChannelingScheme."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.conversational.entities import Intent, IntentResolutionMode, IntentRiskLevel
from domain.conversational.exceptions import IntentNotFoundError
from domain.conversational.ports import IntentRepository


class UpdateIntent:
    def __init__(self, repository: IntentRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        intent_id: str,
        name: str,
        description: Optional[str] = None,
        resolution_mode: Optional[IntentResolutionMode] = None,
        positive_examples: Optional[list[str]] = None,
        negative_examples: Optional[list[str]] = None,
        priority: Optional[int] = None,
        risk_level: Optional[IntentRiskLevel] = None,
        required_variables: Optional[list[str]] = None,
        optional_variables: Optional[list[str]] = None,
        clarifying_questions: Optional[dict[str, str]] = None,
        response_rule: Optional[str] = None,
        fallback_channeling_code: Optional[str] = None,
    ) -> Intent:
        intent = self._repository.get(project_id, intent_id)
        if intent is None:
            raise IntentNotFoundError(project_id, intent_id)
        update: dict = {"name": name, "updated_at": datetime.now(timezone.utc)}
        if description is not None:
            update["description"] = description
        if resolution_mode is not None:
            # model_copy(update=...) NUNCA valida/coacciona -- a
            # diferencia del constructor de Intent (usado por
            # CreateIntent), asignar aquí un string plano tal cual
            # (p. ej. lo que manda ui/conversational/panel.py desde un
            # QComboBox.currentText()) dejaría intent.resolution_mode
            # como str en vez de IntentResolutionMode, rompiendo todo
            # código que espera .value (SqlAlchemyIntentRepository.save,
            # el propio simulador...). Se coacciona explícitamente antes
            # de asignar.
            update["resolution_mode"] = IntentResolutionMode(resolution_mode)
        if positive_examples is not None:
            update["positive_examples"] = list(positive_examples)
        if negative_examples is not None:
            update["negative_examples"] = list(negative_examples)
        if priority is not None:
            update["priority"] = priority
        if risk_level is not None:
            # Mismo motivo que resolution_mode arriba.
            update["risk_level"] = IntentRiskLevel(risk_level)
        if required_variables is not None:
            update["required_variables"] = list(required_variables)
        if optional_variables is not None:
            update["optional_variables"] = list(optional_variables)
        if clarifying_questions is not None:
            update["clarifying_questions"] = dict(clarifying_questions)
        if response_rule is not None:
            update["response_rule"] = response_rule
        if fallback_channeling_code is not None:
            # Cuidado con el doble uso de None en este campo puntual:
            # el propio dominio ya usa None como "sin canalización
            # alternativa" (Intent.fallback_channeling_code), así que
            # no puede reutilizarse también como "no tocar este campo"
            # -- si lo hiciera, nunca sería posible LIMPIAR una
            # canalización alternativa ya asignada desde la edición
            # completa. Por eso el diálogo de edición manda la cadena
            # vacía (nunca None) cuando la persona borra el campo, y
            # aquí, y solo aquí, "" se colapsa a None -- distinto del
            # resto de los campos de texto de este método, donde "" sí
            # es un valor final válido en sí mismo (p. ej. response_rule
            # vacío es una regla de respuesta vacía, no "sin regla").
            update["fallback_channeling_code"] = fallback_channeling_code or None
        updated = intent.model_copy(update=update)
        self._repository.save(updated)
        return updated
