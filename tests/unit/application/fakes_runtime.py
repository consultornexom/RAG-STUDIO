"""Dobles de prueba en memoria para el contexto Runtime (ADR-002, Fase 2/4/5)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from domain.runtime.entities import (
    FAILED_ACTION,
    ChannelingDispatch,
    ConversationLogEntry,
    ConversationMetricsSummary,
    RetrievalFeedbackEntry,
    RetrievalFeedbackSummary,
    WidgetToken,
    latency_percentile,
)
from domain.runtime.ports import (
    ChannelingDispatcher,
    ConversationLogRepository,
    RetrievalFeedbackRepository,
    WidgetTokenRepository,
)


class InMemoryConversationLogRepository(ConversationLogRepository):
    def __init__(self):
        self._entries: list[ConversationLogEntry] = []

    def save(self, entry: ConversationLogEntry) -> None:
        self._entries.append(entry)

    def list_for_project(
        self, project_id: str, limit: int = 100, action: Optional[str] = None,
    ) -> list[ConversationLogEntry]:
        matching = [
            e for e in self._entries
            if e.project_id == project_id and (action is None or e.action == action)
        ]
        return sorted(matching, key=lambda e: e.created_at, reverse=True)[:limit]

    def get_by_id(self, log_id: str) -> Optional[ConversationLogEntry]:
        return next((e for e in self._entries if e.id == log_id), None)

    def list_for_conversation(self, project_id: str, conversation_id: str) -> list[ConversationLogEntry]:
        matching = [
            e for e in self._entries
            if e.project_id == project_id and e.conversation_id == conversation_id
        ]
        return sorted(matching, key=lambda e: e.created_at)

    def count_older_than(self, cutoff: datetime) -> int:
        return sum(1 for e in self._entries if e.created_at < cutoff)

    def delete_older_than(self, cutoff: datetime) -> int:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.created_at >= cutoff]
        return before - len(self._entries)

    def get_metrics_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> ConversationMetricsSummary:
        # Mismo criterio que la implementación SQL real (infrastructure/
        # database/runtime_repositories.py): agrega en Python sobre la
        # lista en memoria, `None` cuando no hay nada que promediar.
        # Percentiles (Ronda 44): mismo latency_percentile puro que usa
        # la implementación SQL, para que ambas compartan exactamente
        # el mismo cálculo.
        matching = [
            e for e in self._entries
            if e.project_id == project_id and (since is None or e.created_at >= since)
        ]
        total_turns = len(matching)
        turns_by_action: dict[str, int] = {}
        for e in matching:
            turns_by_action[e.action] = turns_by_action.get(e.action, 0) + 1
        latencies = [e.latency_ms for e in matching if e.latency_ms is not None and not e.failed]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else None
        failed_turns = turns_by_action.get(FAILED_ACTION, 0)
        attended = total_turns - failed_turns
        abstention_rate = (
            turns_by_action.get("abstenerse", 0) / attended if attended > 0 else None
        )
        return ConversationMetricsSummary(
            project_id=project_id, since=since, total_turns=total_turns,
            turns_by_action=turns_by_action, avg_latency_ms=avg_latency_ms,
            p95_latency_ms=latency_percentile(latencies, 95),
            p99_latency_ms=latency_percentile(latencies, 99),
            abstention_rate=abstention_rate, failed_turns=failed_turns,
            failure_rate=failed_turns / total_turns if total_turns > 0 else None,
        )


class InMemoryWidgetTokenRepository(WidgetTokenRepository):
    def __init__(self):
        self._tokens: dict[str, WidgetToken] = {}

    def save(self, token: WidgetToken) -> None:
        self._tokens[token.id] = token

    def get_by_token(self, token: str) -> Optional[WidgetToken]:
        return next((t for t in self._tokens.values() if t.token == token), None)

    def get_by_id(self, token_id: str) -> Optional[WidgetToken]:
        return self._tokens.get(token_id)

    def list_for_project(self, project_id: str) -> list[WidgetToken]:
        matching = [t for t in self._tokens.values() if t.project_id == project_id]
        return sorted(matching, key=lambda t: t.created_at, reverse=True)


class InMemoryRetrievalFeedbackRepository(RetrievalFeedbackRepository):
    def __init__(self):
        self._entries: list[RetrievalFeedbackEntry] = []

    def save(self, entry: RetrievalFeedbackEntry) -> None:
        # Solo-inserción, igual que la implementación SQL real -- ver
        # el docstring de RetrievalFeedbackEntry.
        self._entries.append(entry)

    def list_for_project(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> list[RetrievalFeedbackEntry]:
        matching = [
            e for e in self._entries
            if e.project_id == project_id and (since is None or e.created_at >= since)
        ]
        return sorted(matching, key=lambda e: e.created_at, reverse=True)

    def list_for_log_entry(self, conversation_log_entry_id: str) -> list[RetrievalFeedbackEntry]:
        matching = [e for e in self._entries if e.conversation_log_entry_id == conversation_log_entry_id]
        return sorted(matching, key=lambda e: e.created_at)

    def get_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> RetrievalFeedbackSummary:
        matching = [
            e for e in self._entries
            if e.project_id == project_id and (since is None or e.created_at >= since)
        ]
        counts_by_signal: dict[str, int] = {}
        counts_by_origin: dict[str, int] = {}
        for e in matching:
            counts_by_signal[e.signal.value] = counts_by_signal.get(e.signal.value, 0) + 1
            counts_by_origin[e.origin.value] = counts_by_origin.get(e.origin.value, 0) + 1
        return RetrievalFeedbackSummary(
            project_id=project_id, since=since, total_entries=len(matching),
            counts_by_signal=counts_by_signal, counts_by_origin=counts_by_origin,
        )


class FakeChannelingDispatcher(ChannelingDispatcher):
    """Registra cada intento de entrega -- no llama a ninguna red.
    `fail_with`, si se configura, hace que `dispatch` levante esa
    excepción en vez de registrar la entrega, para probar que
    `HandleIncomingMessage` no deja que un fallo de canalización rompa
    la respuesta al visitante."""

    def __init__(self, fail_with: Optional[Exception] = None):
        self.calls: list[ChannelingDispatch] = []
        self._fail_with = fail_with

    def dispatch(self, payload: ChannelingDispatch) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.calls.append(payload)
