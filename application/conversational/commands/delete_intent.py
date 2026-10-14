"""Caso de uso: eliminar una intención (ajuste funcional del
2026-09-04, hallazgo real de usuario -- ver bitácora).

El usuario reportó que, tras recibir la edición completa de
guardrails ("Editar regla…" + "Eliminar regla" en la misma ronda
anterior), Guardrails "sí permite tanto editar como eliminar y eso
ayuda mucho en la operación", y preguntó si convenía integrar lo mismo
para intenciones -- ya que "Editar intención…" (ronda anterior) ya
ayuda mucho, pero seguía sin existir ninguna forma de eliminar una
intención, solo desactivarla.

Sin chequeo de "en uso" -- ver domain.conversational.ports.
IntentRepository.delete: ninguna otra entidad de este dominio (ni de
Calidad, ni de Monitoreo) referencia una Intent por id; todas la
referencian por nombre, como texto libre (mismo mecanismo que ya usa
find_rules_referencing_intent). Por eso eliminar una intención tiene
la misma consecuencia -- y solo esa -- que renombrarla: una condición
de guardrail "intencion = <nombre>" deja de cumplirse en silencio. La
interfaz reutiliza el mismo aviso ya existente para el renombrado
antes de confirmar el borrado (ver ui/conversational/panel.py,
_on_delete_intent) -- este comando, a propósito, no lo repite ni lo
bloquea: es una decisión de interfaz, no del dominio."""
from __future__ import annotations

from domain.conversational.exceptions import IntentNotFoundError
from domain.conversational.ports import IntentRepository


class DeleteIntent:
    def __init__(self, repository: IntentRepository):
        self._repository = repository

    def execute(self, project_id: str, intent_id: str) -> None:
        intent = self._repository.get(project_id, intent_id)
        if intent is None:
            raise IntentNotFoundError(project_id, intent_id)
        self._repository.delete(project_id, intent_id)
