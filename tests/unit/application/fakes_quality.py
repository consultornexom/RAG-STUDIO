"""Dobles de prueba en memoria para el contexto Calidad (Etapa 6)."""
from __future__ import annotations

from typing import Optional

from domain.plugins.ports import CustomEvaluator
from domain.quality.entities import EvaluationRun, TestCase
from domain.quality.ports import EvaluationRunRepository, TestCaseRepository


class InMemoryTestCaseRepository(TestCaseRepository):
    def __init__(self):
        self._by_id: dict[str, TestCase] = {}

    def save(self, test_case: TestCase) -> None:
        self._by_id[test_case.id] = test_case

    def get(self, project_id: str, test_case_id: str) -> Optional[TestCase]:
        case = self._by_id.get(test_case_id)
        return case if case and case.project_id == project_id else None

    def list_for_project(self, project_id: str) -> list[TestCase]:
        return [c for c in self._by_id.values() if c.project_id == project_id]

    def delete(self, project_id: str, test_case_id: str) -> None:
        case = self._by_id.get(test_case_id)
        if case is not None and case.project_id == project_id:
            del self._by_id[test_case_id]


class InMemoryEvaluationRunRepository(EvaluationRunRepository):
    def __init__(self):
        self._runs: list[EvaluationRun] = []

    def save(self, run: EvaluationRun) -> None:
        self._runs.append(run)

    def get(self, project_id: str, run_id: str) -> Optional[EvaluationRun]:
        return next((r for r in self._runs if r.project_id == project_id and r.id == run_id), None)

    def list_for_project(self, project_id: str) -> list[EvaluationRun]:
        return sorted(
            (r for r in self._runs if r.project_id == project_id), key=lambda r: r.started_at, reverse=True,
        )

    def get_last_run(self, project_id: str) -> Optional[EvaluationRun]:
        runs = self.list_for_project(project_id)
        return runs[0] if runs else None


# ---------- Complementos EVALUADOR de prueba (Etapa 8 -- ver
# test_run_evaluation.py) ----------
#
# Clases reales e importables (a diferencia de un Mock): RunEvaluation
# las carga vía domain.plugins.loader.load_and_validate, que hace un
# import real por entry_point ("paquete.modulo:Clase"), así que
# necesitan existir como clases de verdad en un módulo real, no como
# dobles construidos en memoria dentro de una prueba.

class AlwaysRejectCustomEvaluator(CustomEvaluator):
    """Rechaza siempre, con un motivo fijo."""

    def evaluate(self, trace, test_case) -> tuple[bool, str]:
        return False, "el evaluador de prueba siempre rechaza"


class AlwaysApproveCustomEvaluator(CustomEvaluator):
    """Aprueba siempre -- para probar que un complemento activo que SÍ
    aprueba no cambia el veredicto."""

    def evaluate(self, trace, test_case) -> tuple[bool, str]:
        return True, "ok"


class BrokenCustomEvaluator(CustomEvaluator):
    """Lanza una excepción al evaluar -- para probar que RunEvaluation
    no se cae por un complemento roto en tiempo de ejecución (a
    diferencia de un entry_point inválido, que se descarta antes,
    al cargar la lista de evaluadores)."""

    def evaluate(self, trace, test_case) -> tuple[bool, str]:
        raise RuntimeError("fallo simulado del evaluador personalizado")
