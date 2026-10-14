"""Caso de uso: eliminar un caso de prueba, bloqueado si ya participó
en alguna corrida de evaluación (Ronda 4, punto 2 de
Validacion_observaciones_RAG_STUDIO.md).

Mismo patrón ya usado en Metadatos (DeleteFieldDefinition/
FieldInUseError) y Catálogos (DeleteCatalogEntry/CatalogEntryInUseError):
se verifica el uso con una sola consulta agregada sobre las corridas del
proyecto (`evaluation_run_repository.list_for_project`, ya es una sola
llamada -- no se repite por cada corrida como si fuera una conexión
nueva, aprendiendo del hallazgo de rendimiento de la Ronda 4 sobre
DeleteFieldDefinition) en vez de bloquear siempre o nunca."""
from __future__ import annotations

from domain.quality.exceptions import TestCaseInUseError, TestCaseNotFoundError
from domain.quality.ports import EvaluationRunRepository, TestCaseRepository


class DeleteTestCase:
    def __init__(self, repository: TestCaseRepository, evaluation_run_repository: EvaluationRunRepository):
        self._repository = repository
        self._evaluation_run_repository = evaluation_run_repository

    def execute(self, project_id: str, test_case_id: str) -> None:
        test_case = self._repository.get(project_id, test_case_id)
        if test_case is None:
            raise TestCaseNotFoundError(project_id, test_case_id)

        for run in self._evaluation_run_repository.list_for_project(project_id):
            if any(item.test_case_id == test_case_id for item in run.items):
                raise TestCaseInUseError(test_case.code)

        self._repository.delete(project_id, test_case_id)
