from __future__ import annotations

from datetime import datetime, timezone

from domain.quality.entities import TestCase
from domain.quality.exceptions import TestCaseNotFoundError
from domain.quality.ports import TestCaseRepository


class SetTestCaseActive:
    def __init__(self, repository: TestCaseRepository):
        self._repository = repository

    def execute(self, project_id: str, test_case_id: str, active: bool) -> TestCase:
        test_case = self._repository.get(project_id, test_case_id)
        if test_case is None:
            raise TestCaseNotFoundError(project_id, test_case_id)
        updated = test_case.model_copy(update={"active": active, "updated_at": datetime.now(timezone.utc)})
        self._repository.save(updated)
        return updated
