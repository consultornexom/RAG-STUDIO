"""Caso de uso: registrar una señal de relevancia sobre una fuente
mostrada en un turno real (Pista C.4a del ADR-003 -- docs proyecto/
RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx, Opción 2 del
documento de decisión C.4).

Cubre tanto el canal operador (panel de Monitoreo, `origin=OPERADOR`)
como el canal del agente conversacional externo (`POST /projects/{id}/
messages/{log_id}/feedback`, `origin=AGENTE_EXTERNO`) -- ambos pasan
por este mismo comando, mismo criterio de "un solo caso de uso, dos
puntos de entrada" que ya usa el resto de `application/`.

Deliberadamente NO ajusta ningún parámetro de búsqueda (RRF, reranker)
-- eso es la Opción 3 de C.4, explícitamente fuera de alcance de esta
pista (ver nota de cierre de C.4a, 2026-08-20)."""
from __future__ import annotations

from typing import Optional

from domain.runtime.entities import FeedbackOrigin, FeedbackSignal, RetrievalFeedbackEntry
from domain.runtime.ports import ConversationLogRepository, RetrievalFeedbackRepository


class ConversationLogEntryNotFoundError(Exception):
    def __init__(self, conversation_log_entry_id: str):
        super().__init__(
            f"No existe ninguna conversación registrada con id {conversation_log_entry_id!r}."
        )
        self.conversation_log_entry_id = conversation_log_entry_id


class RecordRetrievalFeedback:
    def __init__(
        self, log_repository: ConversationLogRepository, feedback_repository: RetrievalFeedbackRepository,
    ):
        self._log_repository = log_repository
        self._feedback_repository = feedback_repository

    def execute(
        self, project_id: str, conversation_log_entry_id: str, source_id: str,
        signal: FeedbackSignal, origin: FeedbackOrigin,
        chunk_id: Optional[str] = None, notes: Optional[str] = None,
    ) -> RetrievalFeedbackEntry:
        # Mismo criterio de validación que PromoteConversationToTestCase:
        # el turno debe existir y pertenecer al proyecto indicado --
        # nunca se guarda una señal "huérfana" sobre un log_id ajeno o
        # inexistente.
        entry = self._log_repository.get_by_id(conversation_log_entry_id)
        if entry is None or entry.project_id != project_id:
            raise ConversationLogEntryNotFoundError(conversation_log_entry_id)

        feedback = RetrievalFeedbackEntry(
            project_id=project_id, conversation_log_entry_id=conversation_log_entry_id,
            source_id=source_id, chunk_id=chunk_id, signal=signal, origin=origin, notes=notes,
        )
        self._feedback_repository.save(feedback)
        return feedback
