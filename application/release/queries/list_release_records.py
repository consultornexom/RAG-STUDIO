from __future__ import annotations

from domain.release.entities import ReleaseRecord
from domain.release.ports import ReleaseRecordRepository


class ListReleaseRecords:
    def __init__(self, repository: ReleaseRecordRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[ReleaseRecord]:
        return self._repository.list_for_project(project_id)
