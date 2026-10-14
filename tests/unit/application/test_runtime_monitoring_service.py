"""Pruebas unitarias de RuntimeMonitoringService (ADR-002, Fase 5;
Ronda 12: purga de retención)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from application.runtime.commands.record_retrieval_feedback import ConversationLogEntryNotFoundError
from application.runtime.service import RuntimeMonitoringService
from domain.projects.entities import Project, ProjectStatus
from domain.quality.entities import TestCategory
from domain.runtime.entities import (
    ConversationLogEntry,
    FeedbackOrigin,
    FeedbackSignal,
    RetrievalFeedbackEntry,
    WidgetToken,
)

from .fakes import InMemoryProjectRepository
from .fakes_quality import InMemoryTestCaseRepository
from .fakes_runtime import (
    InMemoryConversationLogRepository,
    InMemoryRetrievalFeedbackRepository,
    InMemoryWidgetTokenRepository,
)


def _service():
    log_repository = InMemoryConversationLogRepository()
    test_case_repository = InMemoryTestCaseRepository()
    return RuntimeMonitoringService(log_repository, test_case_repository), log_repository, test_case_repository


def _service_with_feedback():
    log_repository = InMemoryConversationLogRepository()
    test_case_repository = InMemoryTestCaseRepository()
    feedback_repository = InMemoryRetrievalFeedbackRepository()
    service = RuntimeMonitoringService(
        log_repository, test_case_repository, feedback_repository=feedback_repository,
    )
    return service, log_repository, feedback_repository


def test_list_conversations_delegates_to_the_repository_with_the_action_filter():
    service, log_repository, _tc = _service()
    log_repository.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="responder"))
    log_repository.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="b", action="canalizar"))

    only_channeled = service.list_conversations("p1", action="canalizar")

    assert [e.message for e in only_channeled] == ["b"]


def test_list_conversations_without_a_filter_returns_everything_for_the_project():
    service, log_repository, _tc = _service()
    log_repository.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="responder"))
    log_repository.save(ConversationLogEntry(project_id="otro", snapshot_version=1, message="b", action="responder"))

    entries = service.list_conversations("p1")

    assert len(entries) == 1
    assert entries[0].message == "a"


def test_list_conversation_thread_returns_only_that_conversations_turns_oldest_first():
    # Ronda 20: RuntimeMonitoringService.list_conversation_thread (Ronda
    # 19) no tenia ninguna prueba propia a nivel de servicio -- solo se
    # verificaba, indirectamente, en el repositorio y via HTTP. Ahora
    # tambien tiene un punto de entrada real en ui/monitoring/panel.py
    # ("Ver conversacion completa...").
    service, log_repository, _tc = _service()
    now = datetime.now(timezone.utc)
    turn_1 = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="primero", action="aclarar",
        conversation_id="conv-1", created_at=now - timedelta(minutes=2),
    )
    turn_2 = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="segundo", action="responder",
        conversation_id="conv-1", created_at=now - timedelta(minutes=1),
    )
    other_conversation = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="otra conversacion", action="responder",
        conversation_id="conv-2", created_at=now,
    )
    for entry in (turn_2, turn_1, other_conversation):  # orden de guardado deliberadamente mezclado
        log_repository.save(entry)

    thread = service.list_conversation_thread("p1", "conv-1")

    assert [e.message for e in thread] == ["primero", "segundo"]


def test_promote_to_test_case_creates_a_real_test_case():
    service, log_repository, test_case_repository = _service()
    entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="¿cuál es el horario?",
        matched_intent="Consultar horario", action="responder",
    )
    log_repository.save(entry)

    test_case = service.promote_to_test_case("p1", entry.id, "MON-001", TestCategory.RESPUESTA_DIRECTA)

    assert test_case_repository.get("p1", test_case.id) == test_case
    assert test_case.query_text == "¿cuál es el horario?"


def test_count_conversations_eligible_for_purge_delegates_to_the_repository():
    service, log_repository, _tc = _service()
    now = datetime.now(timezone.utc)
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=100),
    ))
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="reciente", action="responder",
        created_at=now - timedelta(days=1),
    ))

    assert service.count_conversations_eligible_for_purge(90) == 1


def test_purge_old_conversations_deletes_and_reports_the_count():
    service, log_repository, _tc = _service()
    now = datetime.now(timezone.utc)
    old_entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=100),
    )
    log_repository.save(old_entry)

    deleted = service.purge_old_conversations(90)

    assert deleted == 1
    assert log_repository.get_by_id(old_entry.id) is None


# ================= Pista C.1 del ADR-003: observabilidad básica =================

def test_get_metrics_summary_delegates_to_the_repository():
    service, log_repository, _tc = _service()
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="a", action="responder", latency_ms=100.0,
    ))
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="b", action="abstenerse", latency_ms=300.0,
    ))

    summary = service.get_metrics_summary("p1")

    assert summary.project_id == "p1"
    assert summary.total_turns == 2
    assert summary.turns_by_action == {"responder": 1, "abstenerse": 1}
    assert summary.avg_latency_ms == 200.0
    # Percentiles (Ronda 44): con 2 valores [100, 300], p95/p99 caen
    # ambos en el valor más alto (método de rango más cercano).
    assert summary.p95_latency_ms == 300.0
    assert summary.p99_latency_ms == 300.0
    assert summary.abstention_rate == 0.5


def test_get_metrics_summary_forwards_the_since_window():
    service, log_repository, _tc = _service()
    now = datetime.now(timezone.utc)
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=10),
    ))
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="reciente", action="responder",
        created_at=now,
    ))

    summary = service.get_metrics_summary("p1", since=now - timedelta(days=1))

    assert summary.total_turns == 1


# ================= Pista C.4a del ADR-003: captura de señal de relevancia =================

def test_record_retrieval_feedback_saves_an_entry_with_operator_origin_by_default():
    service, log_repository, feedback_repository = _service_with_feedback()
    entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="a", action="responder",
        source_ids=["src-1"],
    )
    log_repository.save(entry)

    feedback = service.record_retrieval_feedback("p1", entry.id, "src-1", FeedbackSignal.RELEVANTE)

    assert feedback.origin == FeedbackOrigin.OPERADOR
    assert feedback_repository.list_for_log_entry(entry.id) == [feedback]


def test_record_retrieval_feedback_raises_when_the_conversation_does_not_belong_to_the_project():
    service, log_repository, _fb = _service_with_feedback()
    entry = ConversationLogEntry(project_id="otro-proyecto", snapshot_version=1, message="a", action="responder")
    log_repository.save(entry)

    with pytest.raises(ConversationLogEntryNotFoundError):
        service.record_retrieval_feedback("p1", entry.id, "src-1", FeedbackSignal.RELEVANTE)


def test_record_retrieval_feedback_raises_without_a_feedback_repository_configured():
    service, log_repository, _tc = _service()
    entry = ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="responder")
    log_repository.save(entry)

    with pytest.raises(RuntimeError):
        service.record_retrieval_feedback("p1", entry.id, "src-1", FeedbackSignal.RELEVANTE)


def test_get_retrieval_feedback_summary_delegates_to_the_repository():
    service, log_repository, _fb = _service_with_feedback()
    entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="a", action="responder", source_ids=["src-1", "src-2"],
    )
    log_repository.save(entry)
    service.record_retrieval_feedback("p1", entry.id, "src-1", FeedbackSignal.RELEVANTE)
    service.record_retrieval_feedback("p1", entry.id, "src-2", FeedbackSignal.IRRELEVANTE)

    summary = service.get_retrieval_feedback_summary("p1")

    assert summary.total_entries == 2
    assert summary.counts_by_signal == {"relevante": 1, "irrelevante": 1}
    assert summary.counts_by_origin == {"operador": 2}


def test_get_retrieval_feedback_summary_raises_without_a_feedback_repository_configured():
    service, _log_repository, _tc = _service()

    with pytest.raises(RuntimeError):
        service.get_retrieval_feedback_summary("p1")


# ================= Ronda 56: criterios de reapertura (Ronda 45) =================

def _service_with_reopening_criteria():
    log_repository = InMemoryConversationLogRepository()
    test_case_repository = InMemoryTestCaseRepository()
    feedback_repository = InMemoryRetrievalFeedbackRepository()
    project_repository = InMemoryProjectRepository()
    widget_token_repository = InMemoryWidgetTokenRepository()
    service = RuntimeMonitoringService(
        log_repository, test_case_repository, feedback_repository=feedback_repository,
        project_repository=project_repository, widget_token_repository=widget_token_repository,
    )
    return service, log_repository, feedback_repository, project_repository, widget_token_repository


def test_evaluate_reopening_criteria_raises_without_project_and_widget_token_repositories():
    service, _log, _tc = _service()  # sin ninguno de los dos repos nuevos

    with pytest.raises(RuntimeError):
        service.evaluate_reopening_criteria("p1")


def test_alertas_proactivas_no_reunidas_cuando_el_proyecto_no_esta_liberado():
    service, log_repository, _fb, project_repository, widget_token_repository = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente", status=ProjectStatus.EN_PRUEBAS))
    widget_token_repository.save(WidgetToken(project_id="p1"))
    now = datetime.now(timezone.utc)
    for i in range(60):
        log_repository.save(ConversationLogEntry(
            project_id="p1", snapshot_version=1, message=f"m{i}", action="responder",
            created_at=now - timedelta(days=1),
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.proyecto_liberado is False
    assert status.token_widget_activo is True
    assert status.turnos_ultimos_30_dias == 60
    assert status.alertas_proactivas_reunidas is False


def test_alertas_proactivas_no_reunidas_cuando_el_token_esta_revocado():
    service, log_repository, _fb, project_repository, widget_token_repository = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente", status=ProjectStatus.LIBERADO))
    widget_token_repository.save(WidgetToken(project_id="p1", revoked_at=datetime.now(timezone.utc)))
    now = datetime.now(timezone.utc)
    for i in range(60):
        log_repository.save(ConversationLogEntry(
            project_id="p1", snapshot_version=1, message=f"m{i}", action="responder",
            created_at=now - timedelta(days=1),
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.token_widget_activo is False
    assert status.alertas_proactivas_reunidas is False


def test_alertas_proactivas_no_reunidas_por_pocos_turnos_en_los_ultimos_30_dias():
    service, log_repository, _fb, project_repository, widget_token_repository = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente", status=ProjectStatus.LIBERADO))
    widget_token_repository.save(WidgetToken(project_id="p1"))
    now = datetime.now(timezone.utc)
    for i in range(10):  # menos de los 50 requeridos
        log_repository.save(ConversationLogEntry(
            project_id="p1", snapshot_version=1, message=f"m{i}", action="responder",
            created_at=now - timedelta(days=1),
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.turnos_ultimos_30_dias == 10
    assert status.alertas_proactivas_reunidas is False


def test_alertas_proactivas_reunidas_cuando_se_cumplen_las_tres_condiciones():
    service, log_repository, _fb, project_repository, widget_token_repository = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente", status=ProjectStatus.LIBERADO))
    widget_token_repository.save(WidgetToken(project_id="p1"))
    now = datetime.now(timezone.utc)
    for i in range(50):
        log_repository.save(ConversationLogEntry(
            project_id="p1", snapshot_version=1, message=f"m{i}", action="responder",
            created_at=now - timedelta(days=1),
        ))
    # Turnos viejos (fuera de la ventana de 30 dias) no deben contar.
    log_repository.save(ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="vieja", action="responder",
        created_at=now - timedelta(days=45),
    ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.turnos_ultimos_30_dias == 50
    assert status.alertas_proactivas_reunidas is True


def test_aprendizaje_opcion3_no_reunido_sin_ninguna_entrada():
    service, _log, _fb, project_repository, widget_token_repository = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente"))

    status = service.evaluate_reopening_criteria("p1")

    assert status.entradas_feedback_totales == 0
    assert status.fuentes_distintas_en_feedback == 0
    assert status.dias_desde_la_primera_entrada is None
    assert status.aprendizaje_opcion3_reunidas is False


def test_aprendizaje_opcion3_no_reunido_por_pocas_fuentes_distintas():
    service, _log, feedback_repository, project_repository, _tok = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente"))
    now = datetime.now(timezone.utc)
    old_enough = now - timedelta(days=40)
    for i in range(100):
        feedback_repository.save(RetrievalFeedbackEntry(
            project_id="p1", conversation_log_entry_id=f"log-{i}", source_id="src-1",
            signal=FeedbackSignal.RELEVANTE, origin=FeedbackOrigin.OPERADOR, created_at=old_enough,
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.entradas_feedback_totales == 100
    assert status.fuentes_distintas_en_feedback == 1
    assert status.aprendizaje_opcion3_reunidas is False


def test_aprendizaje_opcion3_no_reunido_si_todo_el_volumen_llego_en_los_ultimos_dias():
    service, _log, feedback_repository, project_repository, _tok = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente"))
    now = datetime.now(timezone.utc)
    for i in range(100):
        feedback_repository.save(RetrievalFeedbackEntry(
            project_id="p1", conversation_log_entry_id=f"log-{i}", source_id=f"src-{i % 10}",
            signal=FeedbackSignal.RELEVANTE, origin=FeedbackOrigin.OPERADOR,
            created_at=now - timedelta(days=1),  # todo llegó ayer, sin periodo real de uso
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.fuentes_distintas_en_feedback == 10
    assert status.dias_desde_la_primera_entrada == 1
    assert status.aprendizaje_opcion3_reunidas is False


def test_aprendizaje_opcion3_reunido_cuando_se_cumplen_las_tres_condiciones():
    service, _log, feedback_repository, project_repository, _tok = _service_with_reopening_criteria()
    project_repository.save(Project(id="p1", name="Agente"))
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(days=35)
    for i in range(100):
        feedback_repository.save(RetrievalFeedbackEntry(
            project_id="p1", conversation_log_entry_id=f"log-{i}", source_id=f"src-{i % 10}",
            signal=FeedbackSignal.RELEVANTE, origin=FeedbackOrigin.OPERADOR,
            created_at=oldest if i == 0 else now - timedelta(days=1),
        ))

    status = service.evaluate_reopening_criteria("p1")

    assert status.entradas_feedback_totales == 100
    assert status.fuentes_distintas_en_feedback == 10
    assert status.dias_desde_la_primera_entrada == 35
    assert status.aprendizaje_opcion3_reunidas is True


def test_evaluate_reopening_criteria_trata_un_proyecto_inexistente_como_no_liberado():
    service, _log, _fb, _proj, widget_token_repository = _service_with_reopening_criteria()
    widget_token_repository.save(WidgetToken(project_id="fantasma"))

    status = service.evaluate_reopening_criteria("fantasma")

    assert status.proyecto_liberado is False
    assert status.alertas_proactivas_reunidas is False
