from __future__ import annotations

from datetime import datetime, timezone

from domain.conversational.entities import Intent
from domain.conversational.exceptions import IntentNotFoundError
from domain.conversational.ports import IntentRepository


class SetIntentActive:
    """Activar/Desactivar (RAG STUDIO.odt, catálogo de acciones sobre
    reglas -- el mismo criterio aplica a intenciones: no se borran, se
    desactivan, igual que una fuente rechazada no se borra en el
    contexto Documentos."""

    def __init__(self, repository: IntentRepository):
        self._repository = repository

    def execute(self, project_id: str, intent_id: str, active: bool) -> Intent:
        intent = self._repository.get(project_id, intent_id)
        if intent is None:
            raise IntentNotFoundError(project_id, intent_id)
        updated = intent.model_copy(update={"active": active, "updated_at": datetime.now(timezone.utc)})
        self._repository.save(updated)
        return updated
