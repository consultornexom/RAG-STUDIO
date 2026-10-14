"""Caso de uso: promover una conversación real de la bitácora a un
caso de prueba del banco de calidad (ADR-002, Fase 5 -- "lazo de
mejora continua"). Cierra el círculo que describe el ADR: una
conversación real, atendida por el runtime de producción, se convierte
en un caso de regresión permanente en Calidad (Etapa 6), en vez de
quedar solo como un registro pasivo en `runtime.db`.

Depende directamente de `TestCaseRepository` (vía `CreateTestCase`,
`application/quality/commands/create_test_case.py`), no de todo
`QualityService` -- esta promoción no necesita ejecutar evaluaciones
ni tocar complementos EVALUADOR, solo crear un `TestCase`, mismo
criterio de "dependencias mínimas por comando" que ya usa el resto de
`application/`.

La traducción de `ConversationLogEntry.action` (texto plano de
`domain.runtime`) a `RuleActionType` (enum de `domain.conversational`)
ocurre aquí, a nivel de aplicación -- coordinar dos contextos en la
capa de aplicación ya es el patrón establecido (p. ej.
`application/quality/commands/run_evaluation.py` ya combina
`domain.quality` con `ConversationalService`); lo que `domain.runtime`
nunca debe hacer es importar `domain.conversational` directamente
(ver docstring de `ConversationLogEntry.action`)."""
from __future__ import annotations

from typing import Optional

from application.quality.commands.create_test_case import CreateTestCase
from domain.conversational.entities import RuleActionType
from domain.quality.entities import TestCase, TestCategory, TestSeverity
from domain.quality.ports import TestCaseRepository
from domain.runtime.ports import ConversationLogRepository


class ConversationNotFoundError(Exception):
    def __init__(self, log_id: str):
        super().__init__(f"No existe ninguna conversación registrada con id {log_id!r}.")
        self.log_id = log_id


class PromoteConversationToTestCase:
    def __init__(self, log_repository: ConversationLogRepository, test_case_repository: TestCaseRepository):
        self._log_repository = log_repository
        self._create_test_case = CreateTestCase(test_case_repository)

    def execute(
        self, project_id: str, log_id: str, code: str, category: TestCategory,
        severity: TestSeverity = TestSeverity.MEDIA,
    ) -> TestCase:
        entry = self._log_repository.get_by_id(log_id)
        if entry is None or entry.project_id != project_id:
            raise ConversationNotFoundError(log_id)

        expected_action = self._to_rule_action_type(entry.action)
        return self._create_test_case.execute(
            project_id, code, category, entry.message,
            expected_intent=entry.matched_intent,
            expected_action=expected_action,
            expected_channeling=(entry.action == "canalizar"),
            expected_source_id=entry.source_ids[0] if entry.source_ids else None,
            severity=severity,
        )

    @staticmethod
    def _to_rule_action_type(action: str) -> Optional[RuleActionType]:
        try:
            return RuleActionType(action)
        except ValueError:
            # No debería pasar nunca (HandleIncomingMessage siempre
            # guarda trace.action.value, ya validado por el propio
            # enum) -- pero si algún día cambia el vocabulario de
            # acciones, es mejor promover el caso sin acción esperada
            # que romper la promoción entera.
            return None
