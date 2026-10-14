from __future__ import annotations

from typing import Optional

from domain.release.entities import ReleaseRecord
from domain.release.ports import ReleaseRecordRepository


class GetReleaseRecord:
    def __init__(self, repository: ReleaseRecordRepository):
        self._repository = repository

    def execute(self, project_id: str, record_id: str) -> Optional[ReleaseRecord]:
        return self._repository.get(project_id, record_id)
