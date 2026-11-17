"""Implementación concreta del repositorio del contexto Runtime
(ADR-001, sección 4; ADR-002, Fase 2).

A diferencia de application.db/project.db (dos líneas de migración
Alembic independientes, ADR-001 sección 9), la bitácora de
conversaciones vive en un archivo SQLite propio del runtime, creado
con `Base.metadata.create_all()` en vez de una migración: una fila
puede pertenecer a cualquier proyecto publicado que este proceso esté
atendiendo (no es "un archivo por proyecto" como project.db), y es un
almacén nuevo y aditivo -- si en una fase futura necesita evolucionar
su esquema, se le puede dar su propia línea de migración en ese
momento en vez de anticiparla sin necesidad real todavía."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Float, String, Text, delete, func, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from domain.runtime.entities import (
    FAILED_ACTION,
    ConversationLogEntry,
    ConversationMetricsSummary,
    FeedbackOrigin,
    FeedbackSignal,
    RetrievalFeedbackEntry,
    RetrievalFeedbackSummary,
    WidgetToken,
    latency_percentile,
)
from domain.runtime.ports import ConversationLogRepository, RetrievalFeedbackRepository, WidgetTokenRepository

from .engine import make_session_factory, make_sqlite_engine
from .utc_datetime import UTCDateTime


class RuntimeBase(DeclarativeBase):
    pass


class ConversationLogRecord(RuntimeBase):
    __tablename__ = "conversation_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    """Nullable a nivel de columna (Ronda 19) por compatibilidad con
    filas escritas antes de este campo -- ver
    `_ensure_conversation_id_column` sobre por qué esto no puede ser
    NOT NULL: `create_all()` solo crea TABLAS nuevas, nunca agrega
    columnas a una tabla ya existente, así que un `runtime.db` de una
    instalación anterior necesita una migración explícita (ALTER
    TABLE), y esa columna nace sin valor para las filas ya escritas.
    El dominio (`ConversationLogEntry.conversation_id`) sigue siendo
    obligatorio -- `_record_to_entry` rellena un valor nuevo para
    cualquier fila histórica que llegue con NULL."""
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    snapshot_version: Mapped[int] = mapped_column(nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    matched_intent: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    """list[str] serializado en JSON."""
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    # Ronda 93: correlación y diagnóstico de turnos fallidos. Nullable por
    # compatibilidad con runtime.db anteriores (ver _ensure_diagnostic_columns).
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    error_category: Mapped[str | None] = mapped_column(String, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ronda 104b (Etapa 0): fragmentos entregados EN ORDEN y datos de
    # ejecución (código, instantánea, índice, procedimiento, reranking,
    # texto de búsqueda, filtros). JSON; NULL en filas anteriores.
    chunk_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution: Mapped[str | None] = mapped_column(Text, nullable=True)


_DIAGNOSTIC_COLUMNS = (
    ("trace_id", "VARCHAR"), ("error_category", "VARCHAR"), ("error_stage", "VARCHAR"),
    ("error_code", "VARCHAR"), ("error_summary", "TEXT"), ("error_detail", "TEXT"),
    # Ronda 104b (Etapa 0), mismo criterio aditivo.
    ("chunk_ids", "TEXT"), ("execution", "TEXT"),
)


def _ensure_diagnostic_columns(engine) -> None:
    """Ronda 93: mismo criterio aditivo que `_ensure_conversation_id_column`
    -- agrega las columnas de diagnóstico a un runtime.db existente. Las
    filas anteriores quedan con NULL (turnos exitosos de antes)."""
    inspector = inspect(engine)
    if "conversation_log" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("conversation_log")}
    faltantes = [(nombre, tipo) for nombre, tipo in _DIAGNOSTIC_COLUMNS if nombre not in columns]
    if not faltantes:
        return
    with engine.begin() as connection:
        for nombre, tipo in faltantes:
            connection.execute(text(f"ALTER TABLE conversation_log ADD COLUMN {nombre} {tipo}"))
        if any(nombre == "trace_id" for nombre, _ in faltantes):
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_conversation_log_trace_id ON conversation_log (trace_id)"
            ))


def _ensure_conversation_id_column(engine) -> None:
    """Migración mínima y aditiva (Ronda 19): `create_all()`, arriba,
    solo crea la tabla `conversation_log` si no existe -- en una
    instalación que ya tenía un `runtime.db` de antes de esta ronda, la
    tabla ya existe SIN la columna `conversation_id`, y `create_all()`
    no la agrega (no es una migración, solo declara tablas nuevas). Sin
    este paso, cualquier SELECT/INSERT contra `ConversationLogRecord`
    fallaría con "no such column: conversation_log.conversation_id" en
    cuanto se abriera un runtime.db preexistente. Mismo criterio que el
    resto de este módulo: aditivo, sin Alembic (ver docstring del
    módulo) -- SQLite soporta `ALTER TABLE ... ADD COLUMN` de forma
    directa para una columna nullable nueva."""
    inspector = inspect(engine)
    if "conversation_log" not in inspector.get_table_names():
        return  # Tabla recién creada por create_all() -- ya nace con la columna.
    columns = {col["name"] for col in inspector.get_columns("conversation_log")}
    if "conversation_id" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE conversation_log ADD COLUMN conversation_id VARCHAR"))


class SqlAlchemyConversationLogRepository(ConversationLogRepository):
    def __init__(self, db_path: str | Path):
        self._engine = make_sqlite_engine(Path(db_path))
        RuntimeBase.metadata.create_all(self._engine)
        _ensure_conversation_id_column(self._engine)
        _ensure_diagnostic_columns(self._engine)
        self._session_factory = make_session_factory(self._engine)

    def save(self, entry: ConversationLogEntry) -> None:
        with self._session_factory() as session:
            session.add(ConversationLogRecord(
                id=entry.id, conversation_id=entry.conversation_id,
                project_id=entry.project_id, snapshot_version=entry.snapshot_version,
                message=entry.message, matched_intent=entry.matched_intent, confidence=entry.confidence,
                action=entry.action, response_text=entry.response_text,
                source_ids=json.dumps(entry.source_ids), latency_ms=entry.latency_ms,
                created_at=entry.created_at, trace_id=entry.trace_id,
                error_category=entry.error_category, error_stage=entry.error_stage,
                error_code=entry.error_code, error_summary=entry.error_summary,
                error_detail=entry.error_detail,
                chunk_ids=json.dumps(entry.chunk_ids) if entry.chunk_ids is not None else None,
                execution=json.dumps(entry.execution, ensure_ascii=False) if entry.execution is not None else None,
            ))
            session.commit()

    def list_for_project(
        self, project_id: str, limit: int = 100, action: Optional[str] = None,
    ) -> list[ConversationLogEntry]:
        with self._session_factory() as session:
            query = select(ConversationLogRecord).where(ConversationLogRecord.project_id == project_id)
            if action is not None:
                query = query.where(ConversationLogRecord.action == action)
            records = session.execute(
                query.order_by(ConversationLogRecord.created_at.desc()).limit(limit)
            ).scalars().all()
            return [_record_to_entry(record) for record in records]

    def get_by_id(self, log_id: str) -> Optional[ConversationLogEntry]:
        with self._session_factory() as session:
            record = session.get(ConversationLogRecord, log_id)
            return _record_to_entry(record) if record is not None else None

    def list_for_conversation(self, project_id: str, conversation_id: str) -> list[ConversationLogEntry]:
        with self._session_factory() as session:
            records = session.execute(
                select(ConversationLogRecord)
                .where(
                    ConversationLogRecord.project_id == project_id,
                    ConversationLogRecord.conversation_id == conversation_id,
                )
                .order_by(ConversationLogRecord.created_at.asc())
            ).scalars().all()
            return [_record_to_entry(record) for record in records]

    def count_older_than(self, cutoff: datetime) -> int:
        with self._session_factory() as session:
            return session.execute(
                select(func.count()).select_from(ConversationLogRecord)
                .where(ConversationLogRecord.created_at < cutoff)
            ).scalar_one()

    def delete_older_than(self, cutoff: datetime) -> int:
        with self._session_factory() as session:
            result = session.execute(
                delete(ConversationLogRecord).where(ConversationLogRecord.created_at < cutoff)
            )
            session.commit()
            return result.rowcount

    def get_metrics_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> ConversationMetricsSummary:
        # Pista C.1 del ADR-003 (docs proyecto/
        # RAG_STUDIO_Propuesta_C1_Observabilidad.docx): tres consultas
        # de agregación en SQL, nunca se traen las filas completas a
        # memoria. Tres consultas en vez de una sola porque
        # func.avg/func.count con group_by mezclados en una sola fila
        # de resultado obligarían a "aplanar" el conteo por acción a
        # una sola columna -- más simple y legible como tres queries
        # pequeñas sobre una tabla que ya está indexada por project_id.
        with self._session_factory() as session:
            base_filter = [ConversationLogRecord.project_id == project_id]
            if since is not None:
                base_filter.append(ConversationLogRecord.created_at >= since)

            total_turns = session.execute(
                select(func.count()).select_from(ConversationLogRecord).where(*base_filter)
            ).scalar_one()

            turns_by_action = dict(
                session.execute(
                    select(ConversationLogRecord.action, func.count())
                    .where(*base_filter)
                    .group_by(ConversationLogRecord.action)
                ).all()
            )

            # Ronda 93: los turnos fallidos no son "atendidos": no entran en
            # la tasa de abstención ni en las latencias.
            atendidos_filter = [*base_filter, ConversationLogRecord.action != FAILED_ACTION]
            avg_latency_ms = session.execute(
                select(func.avg(ConversationLogRecord.latency_ms)).where(*atendidos_filter)
            ).scalar_one()

            # Percentiles (Ronda 44, Pista C.5 del ADR-003): se trae SOLO
            # la columna latency_ms (nunca la fila completa) de los
            # turnos con latencia capturada, y se calcula en Python con
            # latency_percentile -- ver el docstring de
            # ConversationMetricsSummary para por qué esta alternativa
            # es aceptable dado el volumen real de una app de
            # escritorio, a diferencia de traer filas completas.
            latencies = session.execute(
                select(ConversationLogRecord.latency_ms)
                .where(*atendidos_filter, ConversationLogRecord.latency_ms.isnot(None))
            ).scalars().all()

            failed_turns = turns_by_action.get(FAILED_ACTION, 0)
            attended_turns = total_turns - failed_turns
            abstention_rate = (
                turns_by_action.get("abstenerse", 0) / attended_turns if attended_turns > 0 else None
            )
            return ConversationMetricsSummary(
                project_id=project_id, since=since, total_turns=total_turns,
                turns_by_action=turns_by_action, avg_latency_ms=avg_latency_ms,
                p95_latency_ms=latency_percentile(latencies, 95),
                p99_latency_ms=latency_percentile(latencies, 99),
                abstention_rate=abstention_rate, failed_turns=failed_turns,
                failure_rate=failed_turns / total_turns if total_turns > 0 else None,
            )


def _record_to_entry(record: ConversationLogRecord) -> ConversationLogEntry:
    # record.conversation_id puede ser None (Ronda 19: filas escritas
    # antes de esta columna, o de la breve ventana en que la columna ya
    # existe pero la fila es de una versión anterior del código) -- el
    # dominio exige un str, así que ConversationLogEntry(...) sin pasar
    # conversation_id usa su propio default_factory (un id nuevo, que
    # no agrupa con nada, pero es lo más honesto que se puede hacer con
    # una fila histórica que nunca tuvo este dato).
    kwargs = dict(
        id=record.id, project_id=record.project_id, snapshot_version=record.snapshot_version,
        message=record.message, matched_intent=record.matched_intent, confidence=record.confidence,
        action=record.action, response_text=record.response_text,
        source_ids=json.loads(record.source_ids), latency_ms=record.latency_ms,
        created_at=record.created_at, trace_id=record.trace_id,
        error_category=record.error_category, error_stage=record.error_stage,
        error_code=record.error_code, error_summary=record.error_summary,
        error_detail=record.error_detail,
        chunk_ids=json.loads(record.chunk_ids) if record.chunk_ids else None,
        execution=json.loads(record.execution) if record.execution else None,
    )
    if record.conversation_id is not None:
        kwargs["conversation_id"] = record.conversation_id
    return ConversationLogEntry(**kwargs)


class WidgetTokenRecord(RuntimeBase):
    __tablename__ = "widget_token"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    max_access_level: Mapped[str | None] = mapped_column(String, nullable=True)
    """Nullable a nivel de columna (Pista B.3 del ADR-003), mismo
    motivo que `ConversationLogRecord.conversation_id` (Ronda 19): un
    `runtime.db` de una instalación anterior a esta capacidad necesita
    una migración explícita (ver `_ensure_max_access_level_column`), y
    esa columna nace sin valor para las filas ya escritas.
    `_record_to_token` rellena "restringido" (sin techo, el valor más
    permisivo) para cualquier fila histórica con NULL -- preserva el
    comportamiento de antes de esta capacidad para tokens ya emitidos."""


def _ensure_max_access_level_column(engine) -> None:
    """Migración mínima y aditiva (Pista B.3), mismo criterio que
    `_ensure_conversation_id_column`: `create_all()` solo crea la
    tabla `widget_token` si no existe -- en una instalación con un
    `runtime.db` de antes de esta capacidad, la tabla ya existe SIN
    esta columna."""
    inspector = inspect(engine)
    if "widget_token" not in inspector.get_table_names():
        return  # Tabla recién creada por create_all() -- ya nace con la columna.
    columns = {col["name"] for col in inspector.get_columns("widget_token")}
    if "max_access_level" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE widget_token ADD COLUMN max_access_level VARCHAR"))


class SqlAlchemyWidgetTokenRepository(WidgetTokenRepository):
    """Vive en el mismo runtime.db que `SqlAlchemyConversationLogRepository`
    (comparten `RuntimeBase`) -- un solo archivo SQLite propio del
    proceso API, no uno por tabla."""

    def __init__(self, db_path: str | Path):
        self._engine = make_sqlite_engine(Path(db_path))
        RuntimeBase.metadata.create_all(self._engine)
        _ensure_max_access_level_column(self._engine)
        self._session_factory = make_session_factory(self._engine)

    def save(self, token: WidgetToken) -> None:
        with self._session_factory() as session:
            session.merge(WidgetTokenRecord(
                id=token.id, project_id=token.project_id, token=token.token,
                created_at=token.created_at, revoked_at=token.revoked_at,
                max_access_level=token.max_access_level,
            ))
            session.commit()

    def get_by_token(self, token: str) -> Optional[WidgetToken]:
        with self._session_factory() as session:
            record = session.execute(
                select(WidgetTokenRecord).where(WidgetTokenRecord.token == token)
            ).scalar_one_or_none()
            return _record_to_token(record) if record is not None else None

    def get_by_id(self, token_id: str) -> Optional[WidgetToken]:
        with self._session_factory() as session:
            record = session.get(WidgetTokenRecord, token_id)
            return _record_to_token(record) if record is not None else None

    def list_for_project(self, project_id: str) -> list[WidgetToken]:
        with self._session_factory() as session:
            records = session.execute(
                select(WidgetTokenRecord)
                .where(WidgetTokenRecord.project_id == project_id)
                .order_by(WidgetTokenRecord.created_at.desc())
            ).scalars().all()
            return [_record_to_token(record) for record in records]


def _record_to_token(record: WidgetTokenRecord) -> WidgetToken:
    # record.max_access_level puede ser None (fila escrita antes de esta
    # columna, o de la breve ventana en que la columna ya existe pero la
    # fila es de una version anterior del codigo) -- WidgetToken.
    # max_access_level ya usa "restringido" (sin techo) como su propio
    # default, asi que basta con no pasarlo para que ese default aplique;
    # mismo criterio que _record_to_entry con conversation_id.
    kwargs = dict(
        id=record.id, project_id=record.project_id, token=record.token,
        created_at=record.created_at, revoked_at=record.revoked_at,
    )
    if record.max_access_level is not None:
        kwargs["max_access_level"] = record.max_access_level
    return WidgetToken(**kwargs)


class RetrievalFeedbackRecord(RuntimeBase):
    """Pista C.4a del ADR-003 -- tabla nueva y aditiva (mismo criterio
    que el resto de este módulo, ver docstring de arriba): no necesita
    ninguna función `_ensure_*_column`, porque `create_all()` la crea
    completa desde cero tanto en una instalación nueva como en un
    `runtime.db` preexistente que todavía no la tiene (a diferencia de
    agregar una columna a una tabla YA existente, que sí lo necesita)."""

    __tablename__ = "retrieval_feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_log_entry_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    signal: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class SqlAlchemyRetrievalFeedbackRepository(RetrievalFeedbackRepository):
    """Vive en el mismo runtime.db que las demás tablas de este módulo
    -- comparten `RuntimeBase`, un solo archivo SQLite por proceso."""

    def __init__(self, db_path: str | Path):
        self._engine = make_sqlite_engine(Path(db_path))
        RuntimeBase.metadata.create_all(self._engine)
        self._session_factory = make_session_factory(self._engine)

    def save(self, entry: RetrievalFeedbackEntry) -> None:
        # Solo INSERT -- nunca UPDATE/merge (ver docstring de
        # RetrievalFeedbackEntry): cada llamada crea una fila nueva,
        # incluso si ya existe una entrada previa para la misma
        # (conversation_log_entry_id, source_id).
        with self._session_factory() as session:
            session.add(RetrievalFeedbackRecord(
                id=entry.id, project_id=entry.project_id,
                conversation_log_entry_id=entry.conversation_log_entry_id,
                source_id=entry.source_id, chunk_id=entry.chunk_id,
                signal=entry.signal.value, origin=entry.origin.value,
                notes=entry.notes, created_at=entry.created_at,
            ))
            session.commit()

    def list_for_project(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> list[RetrievalFeedbackEntry]:
        with self._session_factory() as session:
            query = select(RetrievalFeedbackRecord).where(RetrievalFeedbackRecord.project_id == project_id)
            if since is not None:
                query = query.where(RetrievalFeedbackRecord.created_at >= since)
            records = session.execute(
                query.order_by(RetrievalFeedbackRecord.created_at.desc())
            ).scalars().all()
            return [_record_to_feedback_entry(record) for record in records]

    def list_for_log_entry(self, conversation_log_entry_id: str) -> list[RetrievalFeedbackEntry]:
        with self._session_factory() as session:
            records = session.execute(
                select(RetrievalFeedbackRecord)
                .where(RetrievalFeedbackRecord.conversation_log_entry_id == conversation_log_entry_id)
                .order_by(RetrievalFeedbackRecord.created_at.asc())
            ).scalars().all()
            return [_record_to_feedback_entry(record) for record in records]

    def get_summary(
        self, project_id: str, since: Optional[datetime] = None,
    ) -> RetrievalFeedbackSummary:
        # Mismo criterio de tres consultas pequeñas en vez de una sola
        # que `ConversationLogRepository.get_metrics_summary` -- ver el
        # comentario de ese método sobre por qué.
        with self._session_factory() as session:
            base_filter = [RetrievalFeedbackRecord.project_id == project_id]
            if since is not None:
                base_filter.append(RetrievalFeedbackRecord.created_at >= since)

            total_entries = session.execute(
                select(func.count()).select_from(RetrievalFeedbackRecord).where(*base_filter)
            ).scalar_one()

            counts_by_signal = dict(
                session.execute(
                    select(RetrievalFeedbackRecord.signal, func.count())
                    .where(*base_filter)
                    .group_by(RetrievalFeedbackRecord.signal)
                ).all()
            )

            counts_by_origin = dict(
                session.execute(
                    select(RetrievalFeedbackRecord.origin, func.count())
                    .where(*base_filter)
                    .group_by(RetrievalFeedbackRecord.origin)
                ).all()
            )

            return RetrievalFeedbackSummary(
                project_id=project_id, since=since, total_entries=total_entries,
                counts_by_signal=counts_by_signal, counts_by_origin=counts_by_origin,
            )


def _record_to_feedback_entry(record: RetrievalFeedbackRecord) -> RetrievalFeedbackEntry:
    return RetrievalFeedbackEntry(
        id=record.id, project_id=record.project_id,
        conversation_log_entry_id=record.conversation_log_entry_id,
        source_id=record.source_id, chunk_id=record.chunk_id,
        signal=FeedbackSignal(record.signal), origin=FeedbackOrigin(record.origin),
        notes=record.notes, created_at=record.created_at,
    )
