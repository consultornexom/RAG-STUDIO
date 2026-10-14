"""Puertos del contexto Runtime. Implementados en infrastructure
(ADR-001, sección 4; ADR-002, Fase 2/4)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .entities import (
    ChannelingDispatch,
    ConversationLogEntry,
    ConversationMetricsSummary,
    RetrievalFeedbackEntry,
    RetrievalFeedbackSummary,
    WidgetToken,
)


class ConversationLogRepository(ABC):
    @abstractmethod
    def save(self, entry: ConversationLogEntry) -> None: ...

    @abstractmethod
    def list_for_project(
        self, project_id: str, limit: int = 100, action: Optional[str] = None,
    ) -> list[ConversationLogEntry]:
        """Más recientes primero. `action` (Fase 5, pestaña de
        Monitoreo) filtra opcionalmente por "responder"/"aclarar"/
        "abstenerse"/"canalizar" -- para priorizar, por ejemplo, las
        conversaciones donde el motor no supo responder."""
        ...

    @abstractmethod
    def get_by_id(self, log_id: str) -> Optional[ConversationLogEntry]: ...

    @abstractmethod
    def list_for_conversation(self, project_id: str, conversation_id: str) -> list[ConversationLogEntry]:
        """Todos los turnos de una misma conversación (Ronda 19),
        MÁS ANTIGUOS PRIMERO -- a diferencia de `list_for_project`
        (más recientes primero, pensado para una bandeja de entrada),
        aquí el orden natural es el de lectura de un diálogo de
        principio a fin."""
        ...

    @abstractmethod
    def count_older_than(self, cutoff: datetime) -> int:
        """Cuántas filas tienen `created_at` estrictamente antes de
        `cutoff` -- Ronda 12 (ver Validacion_observaciones_RAG_STUDIO.md,
        brecha de retención de datos): pensado para una vista previa
        ("¿cuánto se borraría?") antes de purgar de verdad con
        `delete_older_than`, sin necesidad de un método separado en
        cada implementación concreta."""
        ...

    @abstractmethod
    def delete_older_than(self, cutoff: datetime) -> int:
        """Borra las filas con `created_at` estrictamente antes de
        `cutoff` y devuelve cuántas se borraron -- ninguna política de
        cuándo llamarlo vive aquí (eso es
        `application.runtime.commands.purge_old_conversations`); este
        puerto solo ejecuta el borrado."""
        ...

    @abstractmethod
    def get_metrics_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> ConversationMetricsSummary:
        """Observabilidad básica (Pista C.1 del ADR-003): agrega
        `latency_ms`/`action` de los turnos de `project_id` -- todo el
        histórico si `since` es `None`, o solo los turnos con
        `created_at >= since` en caso contrario. La agregación ocurre
        en la base de datos (SQL), nunca trayendo todas las filas a
        memoria -- ver la implementación concreta en infrastructure/
        database/runtime_repositories.py."""
        ...


class RetrievalFeedbackRepository(ABC):
    """Pista C.4a del ADR-003 (docs proyecto/
    RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx): señales de
    relevancia (b)/(c) del documento de decisión C.4 -- captura sin
    ningún ajuste automático (Opción 2; la Opción 3 queda fuera de
    alcance de esta pista)."""

    @abstractmethod
    def save(self, entry: RetrievalFeedbackEntry) -> None:
        """Solo inserta -- ninguna implementación debe permitir editar
        ni borrar una entrada ya guardada (ver el docstring de
        `RetrievalFeedbackEntry`)."""
        ...

    @abstractmethod
    def list_for_project(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> list[RetrievalFeedbackEntry]:
        """Más recientes primero."""
        ...

    @abstractmethod
    def list_for_log_entry(self, conversation_log_entry_id: str) -> list[RetrievalFeedbackEntry]:
        """Todas las señales registradas sobre un turno real, en el
        orden en que se guardaron (más antiguas primero) -- quien
        llame decide si le importa solo la más reciente por
        source_id."""
        ...

    @abstractmethod
    def get_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> RetrievalFeedbackSummary:
        """Agregación en SQL (conteos por señal y por origen), mismo
        criterio que `ConversationLogRepository.get_metrics_summary`."""
        ...


class WidgetTokenRepository(ABC):
    @abstractmethod
    def save(self, token: WidgetToken) -> None: ...

    @abstractmethod
    def get_by_token(self, token: str) -> Optional[WidgetToken]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[WidgetToken]:
        """Más recientes primero, incluye los ya revocados (la UI/API
        decide si los muestra u oculta)."""
        ...

    @abstractmethod
    def get_by_id(self, token_id: str) -> Optional[WidgetToken]: ...


class ChannelingDispatcher(ABC):
    """Entrega real de un evento de canalización (Fase 4) -- a un
    correo, CRM, mesa de ayuda o sistema de tickets, según implemente
    cada adaptador concreto. Debe levantar una excepción propia si la
    entrega falla (nunca tragarse el error en silencio); es
    responsabilidad de quien llama (`HandleIncomingMessage`) decidir
    que un fallo de canalización no debe romper la respuesta al
    visitante."""

    @abstractmethod
    def dispatch(self, payload: ChannelingDispatch) -> None: ...
