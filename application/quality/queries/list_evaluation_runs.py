from __future__ import annotations

from domain.quality.entities import EvaluationRun
from domain.quality.ports import EvaluationRunRepository


class ListEvaluationRuns:
    def __init__(self, repository: EvaluationRunRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[EvaluationRun]:
        return self._repository.list_for_project(project_id)
