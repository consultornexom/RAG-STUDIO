"""Puertos del contexto Calidad. Implementados en infrastructure
(ADR-001, sección 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import EvaluationRun, TestCase


class TestCaseRepository(ABC):
    @abstractmethod
    def save(self, test_case: TestCase) -> None: ...

    @abstractmethod
    def get(self, project_id: str, test_case_id: str) -> Optional[TestCase]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[TestCase]: ...

    @abstractmethod
    def delete(self, project_id: str, test_case_id: str) -> None: ...


class EvaluationRunRepository(ABC):
    @abstractmethod
    def save(self, run: EvaluationRun) -> None: ...

    @abstractmethod
    def get(self, project_id: str, run_id: str) -> Optional[EvaluationRun]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[EvaluationRun]: ...

    @abstractmethod
    def get_last_run(self, project_id: str) -> Optional[EvaluationRun]:
        """La corrida más reciente del proyecto (cualquier alcance) --
        base de la comparación de regresión de la siguiente corrida."""
        ...
