"""Ronda 53 (Propuesta de evaluación continua reforzada, opciones B'/C
confirmadas por el consultor): filtra el historial de corridas al
alcance "completa", ordenado más reciente primero.

Se resuelve en application, no en el puerto EvaluationRunRepository:
get_last_run(project_id) deliberadamente ignora el alcance (RunEvaluation
.execute() lo usa así a propósito, para comparar el veredicto de un
caso individual contra la última corrida de CUALQUIER alcance, ver su
docstring) -- cambiar esa semántica para toda la aplicación habría sido
un cambio de comportamiento no solicitado. Comparar Recall@3/MRR entre
corridas SÍ necesita el mismo alcance en ambos lados (una corrida
"completa" y una corrida "individual" de un solo caso no son
comparables), así que este filtro vive aquí, reutilizado tanto por la
nueva compuerta de liberación (evaluate_release_gates.py) como por la
UI (ui/quality/panel.py, comparación y tendencia)."""
from __future__ import annotations

from domain.quality.entities import EvaluationRun
from domain.quality.ports import EvaluationRunRepository


class ListCompleteEvaluationRuns:
    def __init__(self, repository: EvaluationRunRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[EvaluationRun]:
        # list_for_project ya ordena por started_at descendente (ver
        # SqlAlchemyEvaluationRunRepository/InMemoryEvaluationRunRepository)
        # -- solo falta filtrar por alcance.
        return [run for run in self._repository.list_for_project(project_id) if run.scope == "completa"]
