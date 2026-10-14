from __future__ import annotations

from datetime import datetime, timezone

from domain.conversational.entities import ChannelingScheme
from domain.conversational.exceptions import ChannelingSchemeNotFoundError
from domain.conversational.ports import ChannelingSchemeRepository


class SetChannelingSchemeActive:
    def __init__(self, repository: ChannelingSchemeRepository):
        self._repository = repository

    def execute(self, project_id: str, scheme_id: str, active: bool) -> ChannelingScheme:
        scheme = self._repository.get(project_id, scheme_id)
        if scheme is None:
            raise ChannelingSchemeNotFoundError(project_id, scheme_id)
        updated = scheme.model_copy(update={"active": active, "updated_at": datetime.now(timezone.utc)})
        self._repository.save(updated)
        return updated
