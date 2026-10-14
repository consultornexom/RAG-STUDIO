"""Pruebas unitarias de PromoteConversationToTestCase (ADR-002, Fase
5) -- con InMemoryConversationLogRepository e InMemoryTestCaseRepository,
mismo criterio del resto de application/ que no necesita infraestructura
real para probar la lógica de mapeo."""
from __future__ import annotations

import pytest

from application.runtime.commands.promote_conversation_to_test_case import (
    ConversationNotFoundError,
    PromoteConversationToTestCase,
)
from domain.conversational.entities import RuleActionType
from domain.quality.entities import TestCategory, TestSeverity
from domain.runtime.entities import ConversationLogEntry

from .fakes_quality import InMemoryTestCaseRepository
from .fakes_runtime import InMemoryConversationLogRepository


def _promote(entry: ConversationLogEntry, **kwargs):
    log_repository = InMemoryConversationLogRepository()
    log_repository.save(entry)
    test_case_repository = InMemoryTestCaseRepository()
    command = PromoteConversationToTestCase(log_repository, test_case_repository)
    test_case = command.execute(
        entry.project_id, entry.id, kwargs.pop("code", "MON-001"),
        kwargs.pop("category", TestCategory.RESPUESTA_DIRECTA), **kwargs,
    )
    return test_case, test_case_repository


def test_promoting_a_responder_conversation_copies_the_message_and_intent():
    entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="¿cuál es el horario?",
        matched_intent="Consultar horario", confidence=0.9, action="responder",
        source_ids=["s1"],
    )
    test_case, repository = _promote(entry)

    assert test_case.project_id == "p1"
    assert test_case.query_text == "¿cuál es el horario?"
    assert test_case.expected_intent == "Consultar horario"
    assert test_case.expected_action == RuleActionType.RESPONDER
    assert test_case.expected_source_id == "s1"
    assert test_case.expected_channeling is False
    assert repository.get("p1", test_case.id) == test_case


def test_promoting_a_canalizar_conversation_marks_expected_channeling():
    entry = ConversationLogEntry(
        project_id="p1", snapshot_version=1, message="quiero hablar con alguien", action="canalizar",
    )
    test_case, _repository = _promote(entry)

    assert test_case.expected_action == RuleActionType.CANALIZAR
    assert test_case.expected_channeling is True


def test_promoting_a_conversation_without_sources_leaves_expected_source_id_none():
    entry = ConversationLogEntry(project_id="p1", snapshot_version=1, message="hola", action="abstenerse")
    test_case, _repository = _promote(entry)

    assert test_case.expected_source_id is None


def test_promote_uses_the_given_code_category_and_severity():
    entry = ConversationLogEntry(project_id="p1", snapshot_version=1, message="hola", action="responder")
    test_case, _repository = _promote(
        entry, code="MON-042", category=TestCategory.CON_CANALIZACION, severity=TestSeverity.ALTA,
    )

    assert test_case.code == "MON-042"
    assert test_case.category == TestCategory.CON_CANALIZACION
    assert test_case.severity == TestSeverity.ALTA


def test_promote_raises_for_an_unknown_log_id():
    log_repository = InMemoryConversationLogRepository()
    test_case_repository = InMemoryTestCaseRepository()
    command = PromoteConversationToTestCase(log_repository, test_case_repository)

    with pytest.raises(ConversationNotFoundError):
        command.execute("p1", "no-existe", "MON-001", TestCategory.RESPUESTA_DIRECTA)


def test_promote_raises_when_the_log_belongs_to_a_different_project():
    entry = ConversationLogEntry(project_id="otro-proyecto", snapshot_version=1, message="hola", action="responder")
    log_repository = InMemoryConversationLogRepository()
    log_repository.save(entry)
    test_case_repository = InMemoryTestCaseRepository()
    command = PromoteConversationToTestCase(log_repository, test_case_repository)

    with pytest.raises(ConversationNotFoundError):
        command.execute("p1", entry.id, "MON-001", TestCategory.RESPUESTA_DIRECTA)
