"""Fachada de application para el contexto Runtime -- ADR-002, Fase 5
("lazo de mejora continua"): la app de escritorio (pestaña de
Monitoreo) lee la bitácora de conversaciones reales que escribe
`interfaces/api/` (Fase 2) desde el mismo `runtime.db`
(`InstallationPaths.runtime_db_path()`), y puede promover cualquiera
de ellas a un caso de prueba del banco de calidad (Etapa 6).

Deliberadamente NO envuelve `HandleIncomingMessage` ni nada del
proceso API -- eso sigue viviendo solo en `interfaces/api/`; esta
fachada es de solo lectura sobre la bitácora más la escritura de un
caso de prueba nuevo, nada de eso requiere que el proceso API esté
corriendo (`runtime.db` es un archivo SQLite normal, en modo WAL, se
puede leer aunque el runtime esté apagado -- igual que cualquier otro
.db de este proyecto)."""
from __future__ import annotations

from typing import Optional

from datetime import datetime

from domain.projects.ports import ProjectRepository
from domain.quality.entities import TestCase, TestCategory, TestSeverity
from domain.quality.ports import TestCaseRepository
from domain.runtime.entities import (
    ConversationLogEntry,
    ConversationMetricsSummary,
    FeedbackOrigin,
    FeedbackSignal,
    ReopeningCriteriaStatus,
    RetrievalFeedbackEntry,
    RetrievalFeedbackSummary,
)
from domain.runtime.ports import ConversationLogRepository, RetrievalFeedbackRepository, WidgetTokenRepository

from .commands.promote_conversation_to_test_case import PromoteConversationToTestCase
from .commands.purge_old_conversations import PurgeOldConversations
from .commands.record_retrieval_feedback import RecordRetrievalFeedback
from .queries.evaluate_reopening_criteria import EvaluateReopeningCriteria


class RuntimeMonitoringService:
    def __init__(
        self, log_repository: ConversationLogRepository, test_case_repository: TestCaseRepository,
        feedback_repository: Optional[RetrievalFeedbackRepository] = None,
        project_repository: Optional[ProjectRepository] = None,
        widget_token_repository: Optional[WidgetTokenRepository] = None,
    ):
        self._log_repository = log_repository
        self._promote = PromoteConversationToTestCase(log_repository, test_case_repository)
        self._purge = PurgeOldConversations(log_repository)
        # feedback_repository es opcional (Pista C.4a del ADR-003):
        # quien construya este servicio sin necesitar el canal operador
        # de retroalimentación (p. ej. un test que solo cubre C.1) no
        # tiene por qué construir también un RetrievalFeedbackRepository
        # -- mismo criterio ya usado para plugin_repository en
        # QualityService.
        self._feedback_repository = feedback_repository
        self._record_feedback = (
            RecordRetrievalFeedback(log_repository, feedback_repository)
            if feedback_repository is not None else None
        )
        # project_repository/widget_token_repository (Ronda 56):
        # también opcionales, mismo criterio que feedback_repository --
        # solo hacen falta para evaluate_reopening_criteria(), no para
        # el resto de esta fachada. Los tres deben estar presentes (los
        # cuatro repositorios en total, junto con log_repository, que
        # siempre existe) para poder construir EvaluateReopeningCriteria.
        self._project_repository = project_repository
        self._widget_token_repository = widget_token_repository
        self._evaluate_reopening_criteria = (
            EvaluateReopeningCriteria(project_repository, widget_token_repository, log_repository, feedback_repository)
            if project_repository is not None
            and widget_token_repository is not None
            and feedback_repository is not None
            else None
        )

    def list_conversations(
        self, project_id: str, limit: int = 100, action: Optional[str] = None,
    ) -> list[ConversationLogEntry]:
        return self._log_repository.list_for_project(project_id, limit=limit, action=action)

    def list_conversation_thread(self, project_id: str, conversation_id: str) -> list[ConversationLogEntry]:
        """Ronda 19: todos los turnos de UNA conversación (agrupados
        por `conversation_id`), más antiguos primero -- a diferencia de
        `list_conversations` (una bandeja con el turno más reciente de
        cada fila, sin relación entre filas). Antes de esta ronda no
        había ningún campo que permitiera reconstruir esto."""
        return self._log_repository.list_for_conversation(project_id, conversation_id)

    def promote_to_test_case(
        self, project_id: str, log_id: str, code: str, category: TestCategory,
        severity: TestSeverity = TestSeverity.MEDIA,
    ) -> TestCase:
        return self._promote.execute(project_id, log_id, code, category, severity=severity)

    def count_conversations_eligible_for_purge(self, retention_days: int) -> int:
        """Ronda 12: vista previa de cuántas conversaciones se
        borrarían con esta ventana de retención, sin borrar nada."""
        return self._purge.count_eligible(retention_days)

    def purge_old_conversations(self, retention_days: int) -> int:
        """Ronda 12: borra las conversaciones más antiguas que
        `retention_days` de TODOS los proyectos que compartan este
        `runtime.db` -- no depende de ningún proyecto activo, a
        diferencia de `list_conversations`/`promote_to_test_case`."""
        return self._purge.execute(retention_days)

    def get_metrics_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> ConversationMetricsSummary:
        """Pista C.1 del ADR-003 -- observabilidad básica: delega tal
        cual al repositorio (mismo patrón que el resto de esta
        fachada), que agrega en SQL sin traer filas completas a
        memoria."""
        return self._log_repository.get_metrics_summary(project_id, since=since)

    def record_retrieval_feedback(
        self, project_id: str, conversation_log_entry_id: str, source_id: str,
        signal: FeedbackSignal, origin: FeedbackOrigin = FeedbackOrigin.OPERADOR,
        chunk_id: Optional[str] = None, notes: Optional[str] = None,
    ) -> RetrievalFeedbackEntry:
        """Pista C.4a del ADR-003 -- canal operador: marcar una fuente
        mostrada en un turno real como relevante/irrelevante desde el
        panel de Monitoreo. `origin` tiene default OPERADOR porque esta
        fachada es la que usa la app de escritorio -- el canal del
        agente externo (interfaces/api/) construye el
        RetrievalFeedbackEntry directamente con origin=AGENTE_EXTERNO,
        sin pasar por aquí."""
        if self._record_feedback is None:
            raise RuntimeError(
                "Este RuntimeMonitoringService se construyó sin feedback_repository -- "
                "no puede registrar señales de relevancia."
            )
        return self._record_feedback.execute(
            project_id, conversation_log_entry_id, source_id, signal, origin,
            chunk_id=chunk_id, notes=notes,
        )

    def get_retrieval_feedback_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> RetrievalFeedbackSummary:
        """Pista C.4a del ADR-003 -- vista agregada de las señales de
        relevancia ya capturadas, para mostrarse junto al tamaño del
        banco de pruebas (señal a) en el panel de Monitoreo/Calidad."""
        if self._feedback_repository is None:
            raise RuntimeError(
                "Este RuntimeMonitoringService se construyó sin feedback_repository -- "
                "no puede resumir señales de relevancia."
            )
        return self._feedback_repository.get_summary(project_id, since=since)

    def evaluate_reopening_criteria(self, project_id: str) -> ReopeningCriteriaStatus:
        """Ronda 56 -- ver criterios de reapertura de la Ronda 45
        (RAG_STUDIO_Propuesta_Roadmap_RAG5_Pendientes.docx, sección 9):
        computa si ya se cumplen las condiciones para reconsiderar
        alertas proactivas de observabilidad y el aprendizaje del
        retrieval (Opción 3), sin depender de una consulta SQL manual
        repetida cada ronda de consultoría."""
        if self._evaluate_reopening_criteria is None:
            raise RuntimeError(
                "Este RuntimeMonitoringService se construyó sin project_repository/"
                "widget_token_repository -- no puede evaluar los criterios de reapertura."
            )
        return self._evaluate_reopening_criteria.execute(project_id)
