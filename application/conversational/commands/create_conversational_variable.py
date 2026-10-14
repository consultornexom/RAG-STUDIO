from __future__ import annotations

from typing import Optional

from domain.conversational.entities import ConversationalVariable
from domain.conversational.exceptions import DuplicateConversationalCodeError
from domain.conversational.ports import ConversationalVariableRepository


class CreateConversationalVariable:
    def __init__(self, repository: ConversationalVariableRepository):
        self._repository = repository

    def execute(
        self, project_id: str, code: str, label: str, description: str = "",
        metadata_field_id: Optional[str] = None, structured_column: Optional[str] = None,
    ) -> ConversationalVariable:
        code = code.strip()
        if any(existing.code == code for existing in self._repository.list_for_project(project_id)):
            raise DuplicateConversationalCodeError("una variable conversacional", code)
        variable = ConversationalVariable(
            project_id=project_id, code=code, label=label, description=description,
            metadata_field_id=metadata_field_id, structured_column=structured_column,
        )
        self._repository.save(variable)
        return variable
