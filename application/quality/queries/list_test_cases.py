from __future__ import annotations

from domain.quality.entities import TestCase
from domain.quality.ports import TestCaseRepository


class ListTestCases:
    def __init__(self, repository: TestCaseRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[TestCase]:
        return self._repository.list_for_project(project_id)
