"""Excepciones del contexto Calidad."""
from __future__ import annotations


class QualityDomainError(Exception):
    """Base de las excepciones del contexto Calidad."""


class TestCaseNotFoundError(QualityDomainError):
    def __init__(self, project_id: str, test_case_id: str):
        super().__init__(f"No existe el caso de prueba {test_case_id!r} en el proyecto {project_id!r}.")


class EvaluationRunNotFoundError(QualityDomainError):
    def __init__(self, project_id: str, run_id: str):
        super().__init__(f"No existe la corrida de evaluación {run_id!r} en el proyecto {project_id!r}.")


class TestCaseInUseError(QualityDomainError):
    """Ronda 4 (punto 2 de Validacion_observaciones_RAG_STUDIO.md): se
    lanza al intentar eliminar un caso de prueba que ya participó en al
    menos una corrida de evaluación -- borrarlo perdería la trazabilidad
    de esa corrida (EvaluationResultItem.test_case_id quedaría
    apuntando a un caso inexistente). Mismo criterio ya usado para
    campos de metadatos y entradas de catálogo: desactivar en vez de
    perder historial, eliminar libremente solo cuando nunca se usó."""

    def __init__(self, test_case_code: str):
        super().__init__(
            f"No se puede eliminar el caso de prueba {test_case_code!r}: ya participó en al menos una "
            "corrida de evaluación. Si ya no aplica, desactívalo en vez de eliminarlo."
        )
        self.test_case_code = test_case_code


class DuplicateTestCaseCodeError(QualityDomainError):
    """Ronda 88 (2026-10-02, auditoría posterior al hallazgo de importación):
    crear un caso de prueba (o promover una conversación de Monitoreo) con
    un código ya usado mostraba el error crudo de SQLite "UNIQUE constraint
    failed: test_case.project_id, test_case.code"."""

    def __init__(self, code: str):
        super().__init__(
            f"Ya existe un caso de prueba con el código {code!r} en este proyecto. Use otro código."
        )
        self.code = code
