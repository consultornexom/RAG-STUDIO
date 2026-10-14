"""Caso de uso: editar un caso de prueba del banco de calidad (Ronda 4,
punto 2 de Validacion_observaciones_RAG_STUDIO.md).

Antes de esto, el banco de pruebas solo tenía Crear + Activar/
Desactivar -- un caso mal capturado (consulta, dato esperado, acción
prohibida...) no se podía corregir, solo desactivar y dejar acumulado.
`code` no es editable: `RunEvaluation._run_one` lo usa para la
comparación de regresión entre corridas (`previous_verdict_by_code`,
llave = `test_case.code`) -- cambiarlo silenciosamente rompería esa
comparación para corridas ya guardadas, mismo riesgo que se corrigió
para el nombre de una intención (ver update_intent.py /
find_rules_referencing_intent.py) pero aquí evitado de raíz manteniendo
el identificador estable, en vez de agregar un aviso posterior."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.conversational.entities import RuleActionType
from domain.quality.entities import TestCase, TestCategory, TestSeverity
from domain.quality.exceptions import TestCaseNotFoundError
from domain.quality.ports import TestCaseRepository


class UpdateTestCase:
    def __init__(self, repository: TestCaseRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        test_case_id: str,
        category: TestCategory,
        query_text: str,
        provided_variables: Optional[dict[str, str]] = None,
        source_id: Optional[str] = None,
        expected_intent: Optional[str] = None,
        expected_missing_variable: Optional[str] = None,
        expected_action: Optional[RuleActionType] = None,
        forbidden_action: Optional[RuleActionType] = None,
        expected_channeling: bool = False,
        expected_source_id: Optional[str] = None,
        severity: TestSeverity = TestSeverity.MEDIA,
    ) -> TestCase:
        test_case = self._repository.get(project_id, test_case_id)
        if test_case is None:
            raise TestCaseNotFoundError(project_id, test_case_id)

        # TestCase(**data) en vez de model_copy(update=...): model_copy
        # no revalida ni convierte tipos, así que un `expected_action`
        # que llegue como string plano desde la UI (RuleActionType es un
        # str Enum) se quedaría guardado como str en vez de enum --
        # mismo criterio ya aplicado en UpdateProjectName.
        data = test_case.model_dump()
        data.update({
            "category": category, "query_text": query_text,
            "provided_variables": dict(provided_variables or {}), "source_id": source_id,
            "expected_intent": expected_intent, "expected_missing_variable": expected_missing_variable,
            "expected_action": expected_action, "forbidden_action": forbidden_action,
            "expected_channeling": expected_channeling, "expected_source_id": expected_source_id,
            "severity": severity, "updated_at": datetime.now(timezone.utc),
        })
        updated = TestCase(**data)
        self._repository.save(updated)
        return updated
