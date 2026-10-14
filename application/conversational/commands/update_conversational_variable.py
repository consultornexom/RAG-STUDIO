"""Caso de uso: corregir etiqueta/descripción de una variable
conversacional (Ronda 3, punto 13 -- ver update_intent.py, mismo
motivo). `code` no es editable aquí: es la clave que usan
`required_variables`/`optional_variables`/`clarifying_questions` de
Intent y las plantillas de simulación -- cambiarlo silenciosamente
rompería esas referencias, mismo criterio ya aplicado a
FieldDefinition.field_id."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.conversational.entities import ConversationalVariable
from domain.conversational.exceptions import ConversationalVariableNotFoundError
from domain.conversational.ports import ConversationalVariableRepository


class UpdateConversationalVariable:
    def __init__(self, repository: ConversationalVariableRepository):
        self._repository = repository

    def execute(
        self, project_id: str, variable_id: str, label: str, description: Optional[str] = None,
    ) -> ConversationalVariable:
        variable = self._repository.get(project_id, variable_id)
        if variable is None:
            raise ConversationalVariableNotFoundError(project_id, variable_id)
        update = {"label": label, "updated_at": datetime.now(timezone.utc)}
        if description is not None:
            update["description"] = description
        updated = variable.model_copy(update=update)
        self._repository.save(updated)
        return updated
