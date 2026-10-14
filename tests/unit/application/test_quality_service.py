"""Pruebas unitarias de QualityService (fachada de application para el
contexto Calidad, Etapa 6) -- CRUD del banco de pruebas y wiring de
run_evaluation/list_evaluation_runs/get_evaluation_run."""
import pytest

from domain.quality.entities import TestCategory
from domain.quality.exceptions import TestCaseInUseError, TestCaseNotFoundError

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_metadata import InMemorySourceMetadataRepository
from .fakes_quality import InMemoryEvaluationRunRepository, InMemoryTestCaseRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository
from .fakes_ingestion import InMemoryChunkRepository
from application.conversational.service import ConversationalService
from application.quality.service import QualityService
from application.rag.service import RagService


def _make_service() -> QualityService:
    rag_service = RagService(
        InMemoryChunkRepository(), FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
    )
    conversational = ConversationalService(
        InMemoryIntentRepository(), InMemoryConversationalVariableRepository(),
        InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
        InMemorySourceMetadataRepository(), rag_service,
    )
    return QualityService(InMemoryTestCaseRepository(), InMemoryEvaluationRunRepository(), conversational)


def test_create_and_list_test_cases():
    service = _make_service()
    service.create_test_case("p1", "TEST-001", "respuesta_directa", "una consulta cualquiera")
    cases = service.list_test_cases("p1")
    assert len(cases) == 1
    assert cases[0].code == "TEST-001"
    assert cases[0].category == TestCategory.RESPUESTA_DIRECTA
    assert cases[0].active is True


def test_set_test_case_active_toggles_without_deleting():
    service = _make_service()
    case = service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta")
    updated = service.set_test_case_active("p1", case.id, False)
    assert updated.active is False
    assert [c.id for c in service.list_test_cases("p1")] == [case.id]


# ---------- editar/eliminar casos de prueba (Ronda 4, punto 2) ----------

def test_update_test_case_corrects_query_and_expectations():
    service = _make_service()
    case = service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta con typo")
    updated = service.update_test_case(
        "p1", case.id, "sin_informacion", "consulta corregida", expected_action="abstenerse",
    )
    assert updated.code == "TEST-001"  # code no es editable
    assert updated.category == TestCategory.SIN_INFORMACION
    assert updated.query_text == "consulta corregida"
    assert updated.expected_action.value == "abstenerse"


def test_update_test_case_missing_raises():
    service = _make_service()
    with pytest.raises(TestCaseNotFoundError):
        service.update_test_case("p1", "no-existe", "respuesta_directa", "consulta")


def test_delete_test_case_succeeds_when_never_run():
    service = _make_service()
    case = service.create_test_case("p1", "TEST-001", "respuesta_directa", "consulta")
    service.delete_test_case("p1", case.id)
    assert service.list_test_cases("p1") == []


def test_delete_test_case_blocked_when_already_run():
    service = _make_service()
    case = service.create_test_case("p1", "TEST-001", "sin_informacion", "consulta sin relación con nada")
    service.run_evaluation("p1", scope="completa")

    with pytest.raises(TestCaseInUseError):
        service.delete_test_case("p1", case.id)
    # el bloqueo no debe borrar nada a medias
    assert [c.id for c in service.list_test_cases("p1")] == [case.id]


def test_run_evaluation_and_history_wiring():
    service = _make_service()
    service.create_test_case("p1", "TEST-001", "sin_informacion", "consulta sin relación con nada configurado")

    run = service.run_evaluation("p1", scope="completa")
    assert len(run.items) == 1

    assert service.get_evaluation_run("p1", run.id).id == run.id
    assert [r.id for r in service.list_evaluation_runs("p1")] == [run.id]


def test_get_evaluation_run_returns_none_for_unknown_run():
    service = _make_service()
    assert service.get_evaluation_run("p1", "no-existe") is None


# ---------- Ronda 53 (opciones B'/C): list_complete_evaluation_runs / compute_relative_drop ----------

def test_list_complete_evaluation_runs_filters_out_other_scopes():
    service = _make_service()
    service.create_test_case("p1", "TEST-001", "sin_informacion", "consulta A")
    service.create_test_case("p1", "TEST-002", "sin_informacion", "consulta B")

    completa_run = service.run_evaluation("p1", scope="completa")
    individual_run = service.run_evaluation("p1", scope="individual", test_case_id_filter=(
        service.list_test_cases("p1")[0].id
    ))

    complete_runs = service.list_complete_evaluation_runs("p1")
    assert [r.id for r in complete_runs] == [completa_run.id]
    assert individual_run.id not in [r.id for r in complete_runs]


def test_list_complete_evaluation_runs_empty_when_no_runs():
    service = _make_service()
    assert service.list_complete_evaluation_runs("p1") == []


def test_compute_relative_drop_matches_domain_behavior():
    assert QualityService.compute_relative_drop(0.8, 0.6) == pytest.approx(0.25)
    assert QualityService.compute_relative_drop(0.5, 0.9) == 0.0


def test_create_test_case_with_repeated_code_gives_clear_error():
    """Ronda 88 (auditoría): antes terminaba en "UNIQUE constraint failed:
    test_case.project_id, test_case.code" (también al promover una
    conversación de Monitoreo a caso de prueba)."""
    import pytest

    from domain.quality.exceptions import DuplicateTestCaseCodeError

    service = _make_service()
    service.create_test_case("p1", "TEST-001", "respuesta_directa", "una consulta")
    with pytest.raises(DuplicateTestCaseCodeError, match="TEST-001"):
        service.create_test_case("p1", " TEST-001 ", "respuesta_directa", "otra consulta")
