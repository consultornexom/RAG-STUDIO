"""Prueba de integración real de `SqlAlchemyConversationLogRepository`
contra un archivo SQLite real (ADR-002, Fase 5) -- el filtro por
`action` y `get_by_id` son nuevos, pensados para que la pestaña de
Monitoreo de la app de escritorio pueda leer el mismo `runtime.db` que
ya escribe `interfaces/api/`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from domain.runtime.entities import (
    ConversationLogEntry,
    FeedbackOrigin,
    FeedbackSignal,
    RetrievalFeedbackEntry,
    WidgetToken,
)
from infrastructure.database.runtime_repositories import (
    RuntimeBase,
    SqlAlchemyConversationLogRepository,
    SqlAlchemyRetrievalFeedbackRepository,
    SqlAlchemyWidgetTokenRepository,
)


def _entry(project_id="p1", action="responder", message="hola", created_at=None):
    kwargs = {"project_id": project_id, "snapshot_version": 1, "message": message, "action": action}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return ConversationLogEntry(**kwargs)


def test_list_for_project_filters_by_action_when_given(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    responded = _entry(action="responder")
    channeled = _entry(action="canalizar")
    repository.save(responded)
    repository.save(channeled)

    only_channeled = repository.list_for_project("p1", action="canalizar")

    assert [e.id for e in only_channeled] == [channeled.id]


def test_list_for_project_without_an_action_filter_returns_everything(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    repository.save(_entry(action="responder"))
    repository.save(_entry(action="canalizar"))

    all_entries = repository.list_for_project("p1")

    assert len(all_entries) == 2


def test_get_by_id_returns_the_matching_entry(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    entry = _entry()
    repository.save(entry)

    found = repository.get_by_id(entry.id)

    assert found.id == entry.id
    assert found.project_id == entry.project_id
    assert found.message == entry.message
    assert found.action == entry.action


def test_get_by_id_returns_none_for_an_unknown_id(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")

    assert repository.get_by_id("no-existe") is None


def test_the_same_runtime_db_file_is_readable_by_a_second_repository_instance(tmp_path):
    # Mismo escenario real de la Fase 5: interfaces/api/ escribe con
    # una instancia; la app de escritorio (Monitoreo) lee con otra,
    # ambas apuntando al mismo archivo (SQLite en modo WAL, ver
    # infrastructure/database/engine.py).
    db_path = tmp_path / "runtime.db"
    writer = SqlAlchemyConversationLogRepository(db_path)
    entry = _entry()
    writer.save(entry)

    reader = SqlAlchemyConversationLogRepository(db_path)
    found = reader.get_by_id(entry.id)

    assert found.id == entry.id
    assert found.message == entry.message


# ================= Ronda 12: retención/purga =================

def test_count_older_than_only_counts_entries_before_the_cutoff(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    now = datetime.now(timezone.utc)
    old_entry = _entry(created_at=now - timedelta(days=100))
    recent_entry = _entry(created_at=now - timedelta(days=1))
    repository.save(old_entry)
    repository.save(recent_entry)

    count = repository.count_older_than(now - timedelta(days=90))

    assert count == 1


def test_delete_older_than_removes_only_matching_rows_and_returns_the_count(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    now = datetime.now(timezone.utc)
    old_entry = _entry(created_at=now - timedelta(days=100))
    recent_entry = _entry(created_at=now - timedelta(days=1))
    repository.save(old_entry)
    repository.save(recent_entry)

    deleted = repository.delete_older_than(now - timedelta(days=90))

    assert deleted == 1
    assert repository.get_by_id(old_entry.id) is None
    assert repository.get_by_id(recent_entry.id) is not None


def test_delete_older_than_with_nothing_eligible_deletes_nothing(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    entry = _entry(created_at=datetime.now(timezone.utc))
    repository.save(entry)

    deleted = repository.delete_older_than(datetime.now(timezone.utc) - timedelta(days=90))

    assert deleted == 0
    assert repository.get_by_id(entry.id) is not None


# ================= Ronda 19: conversation_id =================

def test_save_persists_the_conversation_id_and_get_by_id_returns_it(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    entry = ConversationLogEntry(
        project_id="p1", conversation_id="conv-1", snapshot_version=1, message="hola", action="responder",
    )
    repository.save(entry)

    found = repository.get_by_id(entry.id)

    assert found.conversation_id == "conv-1"


def test_list_for_conversation_returns_only_matching_turns_oldest_first(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    now = datetime.now(timezone.utc)
    first = ConversationLogEntry(
        project_id="p1", conversation_id="conv-1", snapshot_version=1, message="primero",
        action="aclarar", created_at=now - timedelta(seconds=10),
    )
    second = ConversationLogEntry(
        project_id="p1", conversation_id="conv-1", snapshot_version=1, message="segundo",
        action="responder", created_at=now,
    )
    other_conversation = ConversationLogEntry(
        project_id="p1", conversation_id="conv-2", snapshot_version=1, message="otra conversación",
        action="responder", created_at=now,
    )
    repository.save(first)
    repository.save(second)
    repository.save(other_conversation)

    thread = repository.list_for_conversation("p1", "conv-1")

    assert [entry.id for entry in thread] == [first.id, second.id]


def test_list_for_conversation_scopes_by_project_id_too(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    repository.save(ConversationLogEntry(
        project_id="p1", conversation_id="conv-comun", snapshot_version=1, message="hola", action="responder",
    ))
    repository.save(ConversationLogEntry(
        project_id="p2", conversation_id="conv-comun", snapshot_version=1, message="hola", action="responder",
    ))

    thread = repository.list_for_conversation("p1", "conv-comun")

    assert len(thread) == 1
    assert thread[0].project_id == "p1"


def test_opening_a_pre_round_19_runtime_db_adds_the_missing_column_without_failing(tmp_path):
    # Simula una instalación con un runtime.db escrito por una versión
    # anterior del código -- la tabla existe, pero sin la columna
    # conversation_id (create_all() nunca la habría agregado sola, ver
    # _ensure_conversation_id_column).
    db_path = tmp_path / "runtime.db"
    legacy_engine = create_engine(f"sqlite:///{db_path}", future=True)
    with legacy_engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE conversation_log (
                id VARCHAR PRIMARY KEY,
                project_id VARCHAR NOT NULL,
                snapshot_version INTEGER NOT NULL,
                message TEXT NOT NULL,
                matched_intent VARCHAR,
                confidence FLOAT,
                action VARCHAR NOT NULL,
                response_text TEXT,
                source_ids TEXT NOT NULL DEFAULT '[]',
                latency_ms FLOAT,
                created_at DATETIME NOT NULL
            )
            """
        ))
        connection.execute(text(
            "INSERT INTO conversation_log "
            "(id, project_id, snapshot_version, message, action, source_ids, created_at) "
            "VALUES ('legacy-1', 'p1', 1, 'mensaje antiguo', 'responder', '[]', :created_at)"
        ), {"created_at": datetime.now(timezone.utc).isoformat()})
    legacy_engine.dispose()

    # No debe fallar al abrir -- antes de _ensure_conversation_id_column,
    # esto habría levantado "no such column: conversation_log.conversation_id".
    repository = SqlAlchemyConversationLogRepository(db_path)

    legacy_entry = repository.get_by_id("legacy-1")
    assert legacy_entry is not None
    assert legacy_entry.conversation_id  # se rellenó con un valor nuevo, no quedó vacío ni rompió

    # Y las filas nuevas, después de la migración, sí guardan su propio
    # conversation_id con normalidad.
    new_entry = ConversationLogEntry(
        project_id="p1", conversation_id="conv-nueva", snapshot_version=1, message="mensaje nuevo",
        action="responder",
    )
    repository.save(new_entry)
    assert repository.get_by_id(new_entry.id).conversation_id == "conv-nueva"


def test_ensure_conversation_id_column_is_a_no_op_on_a_fresh_database(tmp_path):
    # Cubre la otra rama de _ensure_conversation_id_column: una tabla
    # recién creada por create_all() ya nace con la columna, así que no
    # debe intentar (y fallar) un segundo ALTER TABLE.
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    RuntimeBase.metadata.create_all(repository._engine)  # idempotente, no debe fallar

    entry = ConversationLogEntry(project_id="p1", conversation_id="conv-1", snapshot_version=1, message="hola", action="responder")
    repository.save(entry)
    assert repository.get_by_id(entry.id).conversation_id == "conv-1"


def test_opening_a_pre_b3_runtime_db_backfills_max_access_level_to_restringido(tmp_path):
    # Mismo escenario que test_opening_a_pre_round_19_runtime_db_...,
    # pero para la columna max_access_level (Pista B.3 del ADR-003,
    # ver _ensure_max_access_level_column): una tabla widget_token
    # escrita por una versión anterior del código no tiene esa columna.
    db_path = tmp_path / "runtime.db"
    legacy_engine = create_engine(f"sqlite:///{db_path}", future=True)
    with legacy_engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE widget_token (
                id VARCHAR PRIMARY KEY,
                project_id VARCHAR NOT NULL,
                token VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                revoked_at DATETIME
            )
            """
        ))
        connection.execute(text(
            "INSERT INTO widget_token (id, project_id, token, created_at) "
            "VALUES ('legacy-token-1', 'p1', 'tok-legacy', :created_at)"
        ), {"created_at": datetime.now(timezone.utc).isoformat()})
    legacy_engine.dispose()

    # No debe fallar al abrir -- antes de _ensure_max_access_level_column,
    # esto habría levantado "no such column: widget_token.max_access_level".
    repository = SqlAlchemyWidgetTokenRepository(db_path)

    legacy_token = repository.get_by_id("legacy-token-1")
    assert legacy_token is not None
    # "restringido" (sin techo) -- preserva exactamente lo que ese
    # token ya podía ver antes de que existiera esta capacidad.
    assert legacy_token.max_access_level == "restringido"

    new_token = WidgetToken(project_id="p1", max_access_level="publico")
    repository.save(new_token)
    assert repository.get_by_id(new_token.id).max_access_level == "publico"


def test_ensure_max_access_level_column_is_a_no_op_on_a_fresh_database(tmp_path):
    # Cubre la otra rama de _ensure_max_access_level_column: una tabla
    # recién creada por create_all() ya nace con la columna.
    repository = SqlAlchemyWidgetTokenRepository(tmp_path / "runtime.db")
    RuntimeBase.metadata.create_all(repository._engine)  # idempotente, no debe fallar

    token = WidgetToken(project_id="p1")
    repository.save(token)
    assert repository.get_by_id(token.id).max_access_level == "restringido"


# ================= Pista C.1 del ADR-003: observabilidad básica =================

def test_get_metrics_summary_aggregates_totals_action_counts_and_average_latency(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="a", action="responder", latency_ms=100.0,
    ))
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="b", action="responder", latency_ms=300.0,
    ))
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="c", action="abstenerse", latency_ms=50.0,
    ))

    summary = repository.get_metrics_summary("p1")

    assert summary.project_id == "p1"
    assert summary.since is None
    assert summary.total_turns == 3
    assert summary.turns_by_action == {"responder": 2, "abstenerse": 1}
    assert summary.avg_latency_ms == 150.0
    # Percentiles (Ronda 44): con 3 valores ordenados [50, 100, 300],
    # p95 y p99 caen ambos en el rango más alto (método de rango más
    # cercano: ceil(0.95*3)=3 y ceil(0.99*3)=3 -> el valor más grande).
    assert summary.p95_latency_ms == 300.0
    assert summary.p99_latency_ms == 300.0
    assert summary.abstention_rate == 1 / 3


def test_get_metrics_summary_percentiles_match_the_nearest_rank_method_over_more_values(tmp_path):
    # 10 valores ordenados 10..100 -- p95 debe caer en la posición
    # ceil(0.95*10)=10 (el valor más alto, 100.0) y p99 en
    # ceil(0.99*10)=10 tambien (100.0) -- mismo calculo que
    # domain.runtime.entities.latency_percentile, verificado aqui
    # contra la implementacion SQL real, no solo contra si misma.
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    for latency in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
        repository.save(ConversationLogEntry(
            project_id="p1", snapshot_version=1, message="x", action="responder", latency_ms=latency,
        ))

    summary = repository.get_metrics_summary("p1")

    assert summary.p95_latency_ms == 100.0
    assert summary.p99_latency_ms == 100.0


def test_get_metrics_summary_scopes_by_project_id(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    repository.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="responder"))
    repository.save(ConversationLogEntry(project_id="p2", snapshot_version=1, message="b", action="responder"))

    summary = repository.get_metrics_summary("p1")

    assert summary.total_turns == 1


def test_get_metrics_summary_filters_by_since_when_given(tmp_path):
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    now = datetime.now(timezone.utc)
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=10),
    ))
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="reciente", action="responder",
        created_at=now,
    ))

    summary = repository.get_metrics_summary("p1", since=now - timedelta(days=1))

    assert summary.total_turns == 1
    assert summary.since == now - timedelta(days=1)


def test_get_metrics_summary_on_an_empty_project_returns_none_averages_not_false_zeros(tmp_path):
    # Mismo criterio que EvaluationRun.recall_at_k (Pista A.1): sin
    # turnos que promediar, el resultado es None, no 0.0 -- un dato
    # falso sería peor que la ausencia de dato.
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")

    summary = repository.get_metrics_summary("proyecto-sin-turnos")

    assert summary.total_turns == 0
    assert summary.turns_by_action == {}
    assert summary.avg_latency_ms is None
    assert summary.p95_latency_ms is None
    assert summary.p99_latency_ms is None
    assert summary.abstention_rate is None


def test_get_metrics_summary_ignores_rows_without_a_captured_latency(tmp_path):
    # Filas históricas sin latency_ms (anteriores a la Ronda 19, o
    # cualquier fila construida sin ese campo) no deben contarse como
    # 0 ms -- func.avg de SQL ya ignora NULL por sí mismo, esta prueba
    # confirma que ese comportamiento llega intacto hasta la entidad.
    repository = SqlAlchemyConversationLogRepository(tmp_path / "runtime.db")
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="sin latencia", action="responder", latency_ms=None,
    ))
    repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="con latencia", action="responder", latency_ms=200.0,
    ))

    summary = repository.get_metrics_summary("p1")

    assert summary.total_turns == 2
    assert summary.avg_latency_ms == 200.0


# ================= Pista C.4a del ADR-003: captura de señal de relevancia =================

def _feedback(project_id="p1", conversation_log_entry_id="log-1", source_id="src-1",
              signal=FeedbackSignal.RELEVANTE, origin=FeedbackOrigin.OPERADOR, created_at=None):
    kwargs = dict(
        project_id=project_id, conversation_log_entry_id=conversation_log_entry_id,
        source_id=source_id, signal=signal, origin=origin,
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    return RetrievalFeedbackEntry(**kwargs)


def test_save_and_list_for_log_entry_round_trips_every_field(tmp_path):
    repository = SqlAlchemyRetrievalFeedbackRepository(tmp_path / "runtime.db")
    entry = RetrievalFeedbackEntry(
        project_id="p1", conversation_log_entry_id="log-1", source_id="src-1", chunk_id="chunk-1",
        signal=FeedbackSignal.CITADO_EN_RESPUESTA, origin=FeedbackOrigin.AGENTE_EXTERNO, notes="nota libre",
    )
    repository.save(entry)

    [loaded] = repository.list_for_log_entry("log-1")

    # Antes de la Ronda 83 (ver Validacion_observaciones_RAG_STUDIO.md),
    # SQLite (DateTime con timezone=True) devolvía created_at SIN tzinfo
    # -- por eso esta prueba comparaba cada campo por separado y
    # created_at aparte, sin exigir tzinfo idéntico. UTCDateTime
    # (infrastructure/database/utc_datetime.py) corrige eso: created_at
    # ahora vuelve UTC-aware, así que la entidad completa ya se puede
    # comparar con `==` como cualquier otra.
    assert loaded == entry


def test_save_never_overwrites_a_previous_entry_for_the_same_source(tmp_path):
    # Solo-inserción (nota de cierre de C.4a, 2026-08-20): dos señales
    # sobre la misma (conversation_log_entry_id, source_id) coexisten,
    # ninguna sustituye a la otra.
    repository = SqlAlchemyRetrievalFeedbackRepository(tmp_path / "runtime.db")
    repository.save(_feedback(signal=FeedbackSignal.IRRELEVANTE))
    repository.save(_feedback(signal=FeedbackSignal.RELEVANTE))

    entries = repository.list_for_log_entry("log-1")

    assert len(entries) == 2
    assert {e.signal for e in entries} == {FeedbackSignal.IRRELEVANTE, FeedbackSignal.RELEVANTE}


def test_legacy_naive_created_at_does_not_break_subtracting_against_an_aware_now(tmp_path):
    # Ronda 83 (ver Validacion_observaciones_RAG_STUDIO.md): mismo
    # defecto de fondo que el reportado en Calidad -> Evaluación, en el
    # camino de "criterios de reapertura" (application/runtime/queries/
    # evaluate_reopening_criteria.py, `(now - primera_entrada).days`).
    # Una fila histórica guardada ANTES de esta corrección (naive en
    # SQLite) no debe romper esa resta contra un `datetime.now(timezone.
    # utc)` aware.
    import sqlite3
    import uuid

    db_path = tmp_path / "runtime.db"
    repository = SqlAlchemyRetrievalFeedbackRepository(db_path)  # crea el esquema

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO retrieval_feedback "
            "(id, project_id, conversation_log_entry_id, source_id, chunk_id, signal, origin, notes, created_at) "
            "VALUES (?, 'p1', 'log-1', 'src-1', NULL, 'relevante', 'operador', NULL, ?)",
            (str(uuid.uuid4()), "2026-08-01 09:00:00.000000"),
        )
        conn.commit()
    finally:
        conn.close()

    [entry] = repository.list_for_project("p1", since=None)
    assert entry.created_at.tzinfo is not None

    now = datetime.now(timezone.utc)
    dias_de_uso = (now - entry.created_at).days  # no debe lanzar TypeError
    assert dias_de_uso >= 0


def test_list_for_project_filters_by_since_and_orders_most_recent_first(tmp_path):
    repository = SqlAlchemyRetrievalFeedbackRepository(tmp_path / "runtime.db")
    now = datetime.now(timezone.utc)
    old = _feedback(conversation_log_entry_id="log-viejo", created_at=now - timedelta(days=10))
    recent = _feedback(conversation_log_entry_id="log-reciente", created_at=now)
    repository.save(old)
    repository.save(recent)

    only_recent = repository.list_for_project("p1", since=now - timedelta(days=1))

    assert [e.id for e in only_recent] == [recent.id]


def test_get_summary_counts_by_signal_and_origin(tmp_path):
    repository = SqlAlchemyRetrievalFeedbackRepository(tmp_path / "runtime.db")
    repository.save(_feedback(source_id="src-1", signal=FeedbackSignal.RELEVANTE, origin=FeedbackOrigin.OPERADOR))
    repository.save(_feedback(source_id="src-2", signal=FeedbackSignal.IRRELEVANTE, origin=FeedbackOrigin.OPERADOR))
    repository.save(_feedback(
        source_id="src-3", signal=FeedbackSignal.CITADO_EN_RESPUESTA, origin=FeedbackOrigin.AGENTE_EXTERNO,
    ))

    summary = repository.get_summary("p1")

    assert summary.total_entries == 3
    assert summary.counts_by_signal == {"relevante": 1, "irrelevante": 1, "citado_en_respuesta": 1}
    assert summary.counts_by_origin == {"operador": 2, "agente_externo": 1}


def test_get_summary_on_an_empty_project_returns_zero_not_an_error(tmp_path):
    repository = SqlAlchemyRetrievalFeedbackRepository(tmp_path / "runtime.db")

    summary = repository.get_summary("proyecto-sin-senales")

    assert summary.total_entries == 0
    assert summary.counts_by_signal == {}
    assert summary.counts_by_origin == {}


def test_retrieval_feedback_table_is_created_fresh_alongside_the_conversation_log_table(tmp_path):
    # Tabla nueva y aditiva (ver docstring de RetrievalFeedbackRecord):
    # crear primero el repositorio de conversaciones y despues el de
    # feedback contra el MISMO archivo no debe fallar ni perder nada.
    db_path = tmp_path / "runtime.db"
    log_repository = SqlAlchemyConversationLogRepository(db_path)
    log_repository.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="responder"))

    feedback_repository = SqlAlchemyRetrievalFeedbackRepository(db_path)
    feedback_repository.save(_feedback())

    assert len(feedback_repository.list_for_project("p1")) == 1
    assert len(log_repository.list_for_project("p1")) == 1
