from __future__ import annotations

from typing import Optional

from domain.conversational.entities import ChannelingMedium, ChannelingScheme
from domain.conversational.exceptions import DuplicateConversationalCodeError
from domain.conversational.ports import ChannelingSchemeRepository


class CreateChannelingScheme:
    def __init__(self, repository: ChannelingSchemeRepository):
        self._repository = repository

    def execute(
        self, project_id: str, code: str, name: str, reason: str = "", condition: str = "",
        target_area: str = "", priority: int = 0,
        required_data: Optional[list[str]] = None, allowed_data: Optional[list[str]] = None,
        forbidden_data: Optional[list[str]] = None, summary_template: str = "",
        medium: ChannelingMedium = ChannelingMedium.REGISTRO_MANUAL,
        user_message: str = "", alternative_action: str = "",
    ) -> ChannelingScheme:
        code = code.strip()
        if self._repository.get_by_code(project_id, code) is not None:
            raise DuplicateConversationalCodeError("un esquema de canalización", code)
        scheme = ChannelingScheme(
            project_id=project_id, code=code, name=name, reason=reason, condition=condition,
            target_area=target_area, priority=priority,
            required_data=list(required_data or []), allowed_data=list(allowed_data or []),
            forbidden_data=list(forbidden_data or []), summary_template=summary_template,
            medium=medium, user_message=user_message, alternative_action=alternative_action,
        )
        self._repository.save(scheme)
        return scheme
