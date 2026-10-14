"""Fachada de application para el contexto Calidad (Etapa 6)."""
from __future__ import annotations

from typing import Callable, Optional

from application.conversational.service import ConversationalService
from domain.plugins.ports import PluginRepository
from domain.quality.entities import (
    EvaluationRun, RetrievalRegressionComparison, TestCase, TestCategory, compare_retrieval_regression,
    relative_drop,
)
from domain.quality.ports import EvaluationRunRepository, TestCaseRepository

from .commands.create_test_case import CreateTestCase
from .commands.delete_test_case import DeleteTestCase
from .commands.run_evaluation import RunEvaluation
from .commands.set_test_case_active import SetTestCaseActive
from .commands.update_test_case import UpdateTestCase
from .queries.get_evaluation_run import GetEvaluationRun
from .queries.list_complete_evaluation_runs import ListCompleteEvaluationRuns
from .queries.list_evaluation_runs import ListEvaluationRuns
from .queries.list_test_cases import ListTestCases


class QualityService:
    def __init__(
        self, test_case_repository: TestCaseRepository, evaluation_run_repository: EvaluationRunRepository,
        conversational_service: ConversationalService, plugin_repository: Optional[PluginRepository] = None,
    ):
        # plugin_repository es opcional (igual que embedding_provider_factory
        # en RagService): sin él, RunEvaluation no invoca complementos
        # EVALUADOR (Etapa 8) y se comporta exactamente como antes.
        self._create_test_case = CreateTestCase(test_case_repository)
        self._set_test_case_active = SetTestCaseActive(test_case_repository)
        self._update_test_case = UpdateTestCase(test_case_repository)
        self._delete_test_case = DeleteTestCase(test_case_repository, evaluation_run_repository)
        self._list_test_cases = ListTestCases(test_case_repository)
        self._run_evaluation = RunEvaluation(
            test_case_repository, evaluation_run_repository, conversational_service,
            plugin_repository=plugin_repository,
        )
        self._list_runs = ListEvaluationRuns(evaluation_run_repository)
        self._list_complete_runs = ListCompleteEvaluationRuns(evaluation_run_repository)
        self._get_run = GetEvaluationRun(evaluation_run_repository)

    # ---------- banco de pruebas ----------
    def create_test_case(
        self, project_id: str, code: str, category: TestCategory, query_text: str, **kwargs
    ) -> TestCase:
        return self._create_test_case.execute(project_id, code, category, query_text, **kwargs)

    def set_test_case_active(self, project_id: str, test_case_id: str, active: bool) -> TestCase:
        return self._set_test_case_active.execute(project_id, test_case_id, active)

    def update_test_case(
        self, project_id: str, test_case_id: str, category: TestCategory, query_text: str, **kwargs
    ) -> TestCase:
        """Ronda 4 (punto 2): edición completa salvo `code` -- ver
        UpdateTestCase."""
        return self._update_test_case.execute(project_id, test_case_id, category, query_text, **kwargs)

    def delete_test_case(self, project_id: str, test_case_id: str) -> None:
        """Ronda 4 (punto 2): bloqueado si el caso ya participó en
        alguna corrida de evaluación -- ver DeleteTestCase/
        TestCaseInUseError."""
        self._delete_test_case.execute(project_id, test_case_id)

    def list_test_cases(self, project_id: str) -> list[TestCase]:
        return self._list_test_cases.execute(project_id)

    # ---------- evaluación ----------
    def run_evaluation(
        self, project_id: str, scope: str = "completa", category_filter: Optional[TestCategory] = None,
        test_case_id_filter: Optional[str] = None, is_cancelled: Callable[[], bool] = lambda: False,
    ) -> EvaluationRun:
        return self._run_evaluation.execute(
            project_id, scope=scope, category_filter=category_filter, test_case_id_filter=test_case_id_filter,
            is_cancelled=is_cancelled,
        )

    def list_evaluation_runs(self, project_id: str) -> list[EvaluationRun]:
        return self._list_runs.execute(project_id)

    def list_complete_evaluation_runs(self, project_id: str) -> list[EvaluationRun]:
        """Ronda 53 (opciones B'/C): solo corridas de alcance "completa",
        más reciente primero -- las únicas comparables entre sí para
        Recall@3/MRR agregado (ver ListCompleteEvaluationRuns)."""
        return self._list_complete_runs.execute(project_id)

    @staticmethod
    def compute_relative_drop(reference: float, current: float) -> float:
        """Envoltorio delgado de domain.quality.entities.relative_drop
        (Ronda 53): existe para que ui/quality/panel.py -- que por regla
        de capa solo llama a application, nunca a domain (ver su
        docstring) -- pueda mostrar exactamente el mismo cálculo que usa
        _retrieval_regression_gate, sin importar domain directamente."""
        return relative_drop(reference, current)

    @staticmethod
    def compare_retrieval_regression(current: EvaluationRun, reference: EvaluationRun) -> RetrievalRegressionComparison:
        """Envoltorio delgado de domain.quality.entities.
        compare_retrieval_regression (Ronda 84, hallazgo real de
        usuario): mismo criterio que compute_relative_drop -- existe
        para que ui/quality/panel.py pueda clasificar exactamente la
        misma situación (sin métricas todavía / solo la más reciente /
        ambas comparables) que usa _retrieval_regression_gate, sin
        importar domain directamente."""
        return compare_retrieval_regression(current, reference)

    def get_evaluation_run(self, project_id: str, run_id: str) -> Optional[EvaluationRun]:
        return self._get_run.execute(project_id, run_id)
