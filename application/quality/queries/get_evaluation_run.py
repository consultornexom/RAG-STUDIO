from __future__ import annotations

from typing import Optional

from domain.quality.entities import EvaluationRun
from domain.quality.ports import EvaluationRunRepository


class GetEvaluationRun:
    def __init__(self, repository: EvaluationRunRepository):
        self._repository = repository

    def execute(self, project_id: str, run_id: str) -> Optional[EvaluationRun]:
        return self._repository.get(project_id, run_id)
