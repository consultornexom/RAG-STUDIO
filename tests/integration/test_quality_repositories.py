"""Pruebas de integración reales (SQLite vía Alembic) de los 2
repositorios del contexto Calidad (Etapa 6)."""
import pytest
from sqlalchemy.exc import IntegrityError

from domain.conversational.entities import RuleActionType
from domain.quality.entities import (
    EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCase, TestCategory, TestSeverity,
)
from infrastructure.database.quality_repositories import (
    SqlAlchemyEvaluationRunRepository, SqlAlchemyTestCaseRepository,
)
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_test_case_round_trip_preserves_all_fields(tmp_path):
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case = TestCase(
        project_id="p1", code="TEST-ADM-001", category=TestCategory.RESPUESTA_CONDICIONADA,
        query_text="qué requisitos necesito", provided_variables={"programa": "Ingeniería"},
        source_id="s1", expected_intent="consultar requisitos", expected_missing_variable="plantel",
        expected_action=RuleActionType.ACLARAR, forbidden_action=RuleActionType.RESPONDER,
        expected_channeling=True, expected_source_id="s1", severity=TestSeverity.ALTA,
    )
    repo.save(case)

    fetched = repo.get("p1", case.id)
    assert fetched is not None
    assert fetched.code == "TEST-ADM-001"
    assert fetched.category == TestCategory.RESPUESTA_CONDICIONADA
    assert fetched.provided_variables == {"programa": "Ingeniería"}
    assert fetched.expected_missing_variable == "plantel"
    assert fetched.expected_action == RuleActionType.ACLARAR
    assert fetched.forbidden_action == RuleActionType.RESPONDER
    assert fetched.expected_channeling is True
    assert fetched.severity == TestSeverity.ALTA
    assert fetched.active is True


def test_test_case_save_upserts_by_id(tmp_path):
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case = TestCase(project_id="p1", code="TEST-001", category=TestCategory.SEGURIDAD, query_text="x")
    repo.save(case)
    updated = case.model_copy(update={"active": False})
    repo.save(updated)

    fetched = repo.get("p1", case.id)
    assert fetched.active is False
    assert len(repo.list_for_project("p1")) == 1


def test_test_case_get_returns_none_for_wrong_project(tmp_path):
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case = TestCase(project_id="p1", code="TEST-001", category=TestCategory.SEGURIDAD, query_text="x")
    repo.save(case)
    assert repo.get("p2", case.id) is None


def test_test_case_delete_removes_it(tmp_path):
    # Ronda 4 (punto 2 de Validacion_observaciones_RAG_STUDIO.md).
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case = TestCase(project_id="p1", code="TEST-001", category=TestCategory.SEGURIDAD, query_text="x")
    repo.save(case)

    repo.delete("p1", case.id)

    assert repo.get("p1", case.id) is None
    assert repo.list_for_project("p1") == []


def test_test_case_code_must_be_unique_per_project(tmp_path):
    # Auditoría Ronda 48 (pruebas reales con documentos de
    # Licenciatura/), hallazgo menor #162, corregido en la Ronda 51
    # (migración 0017, índice único uq_test_case_code): dos casos de
    # prueba distintos (id distinto) con el mismo project_id+code ya no
    # se pueden guardar los dos -- antes de esta corrección, esto no
    # lanzaba ningún error y volvía ambiguo un reporte de evaluación.
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    first = TestCase(project_id="p1", code="UDL-001", category=TestCategory.SEGURIDAD, query_text="x")
    second = TestCase(project_id="p1", code="UDL-001", category=TestCategory.SEGURIDAD, query_text="y")
    repo.save(first)

    with pytest.raises(IntegrityError):
        repo.save(second)


def test_test_case_same_code_is_allowed_across_different_projects(tmp_path):
    # El índice único es por (project_id, code) -- dos proyectos
    # distintos sí pueden reutilizar el mismo code, igual criterio que
    # uq_channeling_scheme_code.
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case_p1 = TestCase(project_id="p1", code="UDL-001", category=TestCategory.SEGURIDAD, query_text="x")
    case_p2 = TestCase(project_id="p2", code="UDL-001", category=TestCategory.SEGURIDAD, query_text="y")
    repo.save(case_p1)
    repo.save(case_p2)  # no debe lanzar

    assert repo.get("p1", case_p1.id) is not None
    assert repo.get("p2", case_p2.id) is not None


def test_test_case_delete_ignores_wrong_project(tmp_path):
    repo = SqlAlchemyTestCaseRepository(_paths(tmp_path))
    case = TestCase(project_id="p1", code="TEST-001", category=TestCategory.SEGURIDAD, query_text="x")
    repo.save(case)

    repo.delete("p2", case.id)  # no debe borrar la fuente de otro proyecto

    assert repo.get("p1", case.id) is not None


def test_evaluation_run_round_trip_preserves_items(tmp_path):
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    run = EvaluationRun(
        project_id="p1", scope="completa",
        items=[
            EvaluationResultItem(
                test_case_id="tc1", test_case_code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
                verdict=EvaluationVerdict.ROJO, actual_intent="consultar requisitos",
                actual_action=RuleActionType.RESPONDER, mismatches=["se ejecutó la acción prohibida"],
                regressed=True,
            ),
        ],
    )
    repo.save(run)

    fetched = repo.get("p1", run.id)
    assert fetched is not None
    assert fetched.scope == "completa"
    assert len(fetched.items) == 1
    item = fetched.items[0]
    assert item.test_case_code == "TEST-001"
    assert item.verdict == EvaluationVerdict.ROJO
    assert item.actual_action == RuleActionType.RESPONDER
    assert item.mismatches == ["se ejecutó la acción prohibida"]
    assert item.regressed is True
    assert fetched.has_blocking_failures is True


def test_evaluation_run_round_trip_preserves_retrieval_check_fields(tmp_path):
    """Ronda 53: corrige una brecha real de persistencia -- antes de
    esta ronda, retrieval_check_applicable/expected_source_rank se
    perdían en cualquier corrida releída de BD (ver migración 0018 y
    Validacion_observaciones_RAG_STUDIO.md, Ronda 53), así que
    recall_at_k()/mean_reciprocal_rank() volvían None sin razón real
    para cualquier corrida que no fuera el objeto recién creado en
    memoria."""
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    run = EvaluationRun(
        project_id="p1", scope="completa",
        items=[
            EvaluationResultItem(
                test_case_id="tc1", test_case_code="TEST-001", category=TestCategory.RESPUESTA_DIRECTA,
                verdict=EvaluationVerdict.VERDE, retrieval_check_applicable=True, expected_source_rank=1,
            ),
            EvaluationResultItem(
                test_case_id="tc2", test_case_code="TEST-002", category=TestCategory.RESPUESTA_DIRECTA,
                verdict=EvaluationVerdict.AMARILLO, retrieval_check_applicable=True, expected_source_rank=None,
            ),
            EvaluationResultItem(
                test_case_id="tc3", test_case_code="TEST-003", category=TestCategory.SEGURIDAD,
                verdict=EvaluationVerdict.VERDE,
            ),
        ],
    )
    repo.save(run)

    fetched = repo.get("p1", run.id)
    assert fetched is not None
    by_code = {item.test_case_code: item for item in fetched.items}
    assert by_code["TEST-001"].retrieval_check_applicable is True
    assert by_code["TEST-001"].expected_source_rank == 1
    assert by_code["TEST-002"].retrieval_check_applicable is True
    assert by_code["TEST-002"].expected_source_rank is None
    assert by_code["TEST-003"].retrieval_check_applicable is False
    assert by_code["TEST-003"].expected_source_rank is None
    # La razón de ser de esta prueba: recall_at_k/MRR deben sobrevivir
    # el roundtrip, no solo funcionar sobre el objeto recién creado.
    assert fetched.recall_at_k(3) == 0.5
    assert fetched.mean_reciprocal_rank() == 0.5


def test_evaluation_run_list_for_project_orders_most_recent_first(tmp_path):
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    from datetime import datetime, timedelta, timezone
    older = EvaluationRun(project_id="p1", started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    newer = EvaluationRun(project_id="p1", started_at=datetime.now(timezone.utc))
    repo.save(older)
    repo.save(newer)

    runs = repo.list_for_project("p1")
    assert [r.id for r in runs] == [newer.id, older.id]


def test_evaluation_run_get_last_run_returns_most_recent(tmp_path):
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    from datetime import datetime, timedelta, timezone
    older = EvaluationRun(project_id="p1", started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    newer = EvaluationRun(project_id="p1", started_at=datetime.now(timezone.utc))
    repo.save(older)
    repo.save(newer)

    assert repo.get_last_run("p1").id == newer.id


def test_evaluation_run_get_last_run_returns_none_when_no_runs(tmp_path):
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    assert repo.get_last_run("p1") is None


def _insert_legacy_naive_run(paths, project_id: str, started_at_naive_text: str) -> str:
    """Simula una fila guardada ANTES de la corrección de la Ronda 83
    (ver Validacion_observaciones_RAG_STUDIO.md): un `started_at` naive
    tal como quedaba sin `UTCDateTime` -- se inserta directo por sqlite3
    para no pasar por la normalización que se está probando."""
    import sqlite3
    import uuid

    from infrastructure.database.migrations import ensure_project_db

    db_path = ensure_project_db(paths, project_id)
    run_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO evaluation_run "
            "(id, project_id, scope, category_filter, test_case_id_filter, started_at, finished_at) "
            "VALUES (?, ?, 'completa', NULL, NULL, ?, ?)",
            (run_id, project_id, started_at_naive_text, started_at_naive_text),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def test_evaluation_run_started_at_round_trips_as_utc_aware(tmp_path):
    # Ronda 83 (hallazgo real de usuario, ver bitácora): antes de esta
    # corrección, un EvaluationRun guardado con started_at aware volvía
    # NAIVE al releerse de SQLite (el dialecto de SQLite ignora tzinfo al
    # serializar), aunque la columna esté declarada con
    # DateTime(timezone=True). UTCDateTime (infrastructure/database/
    # utc_datetime.py) corrige esto -- se confirma aquí releyendo una
    # corrida recién guardada.
    repo = SqlAlchemyEvaluationRunRepository(_paths(tmp_path))
    run = EvaluationRun(project_id="p1", scope="completa")
    repo.save(run)

    fetched = repo.get("p1", run.id)
    assert fetched is not None
    assert fetched.started_at.tzinfo is not None


def test_evaluation_run_legacy_naive_row_round_trips_as_utc_aware(tmp_path):
    # Complementa la prueba anterior: un registro histórico guardado
    # ANTES de esta corrección (naive en la base de datos, sin haber
    # pasado nunca por UTCDateTime) debe seguir siendo compatible sin
    # requerir recrear el proyecto -- ver criterios de aceptación del
    # ajuste. UTCDateTime le reatribuye tzinfo=utc al releerlo.
    paths = _paths(tmp_path)
    repo = SqlAlchemyEvaluationRunRepository(paths)
    legacy_run_id = _insert_legacy_naive_run(paths, "p1", "2026-08-01 09:00:00.000000")

    fetched = repo.get("p1", legacy_run_id)
    assert fetched is not None
    assert fetched.started_at.tzinfo is not None


def test_evaluation_run_regression_comparison_does_not_raise_with_mixed_naive_and_aware_rows(tmp_path):
    # Reproduce exactamente el reporte real del usuario: una corrida
    # "completa" histórica (naive en BD, como quedaba antes de esta
    # Ronda) y una corrida "completa" nueva, recién guardada -- comparar
    # started_at entre ambas (la misma expresión de
    # ui/quality/panel.py::_render_regression_comparison,
    # `r.started_at < run.started_at`) no debe lanzar
    # "TypeError: can't compare offset-naive and offset-aware datetimes".
    from datetime import datetime, timezone

    paths = _paths(tmp_path)
    repo = SqlAlchemyEvaluationRunRepository(paths)
    _insert_legacy_naive_run(paths, "p1", "2026-08-01 09:00:00.000000")
    newest = EvaluationRun(project_id="p1", scope="completa", started_at=datetime.now(timezone.utc))
    repo.save(newest)

    complete_runs = repo.list_for_project("p1")
    assert len(complete_runs) == 2
    older = [r for r in complete_runs if r.id != newest.id and r.started_at < newest.started_at]
    assert len(older) == 1
