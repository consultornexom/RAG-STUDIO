"""Ronda 84 (hallazgo real de usuario, ver bitácora): el mensaje de
"Comparación con la corrida completa anterior" en Calidad -> Evaluación
usaba un `if current_recall is None or reference_recall is None` local
que confundía "ninguna corrida tiene fuente esperada" con "solo la
corrida de referencia no la tiene" -- un caso muy distinto y engañoso,
ya que la corrida más reciente sí había calculado métricas reales.
Corregido delegando la clasificación a
QualityService.compare_retrieval_regression (domain.quality.entities.
compare_retrieval_regression), el mismo cálculo que usa
EvaluateReleaseGates._retrieval_regression_gate en Liberación.

Mismo criterio de omisión automática sin Qt que el resto de
tests/unit/ui/ -- no ejecutable en este sandbox de consultoría por la
carencia de libEGL.so.1 ya documentada en rondas anteriores."""
import os
from datetime import datetime, timezone

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(
        f"Qt no disponible en este entorno ({exc}); se omite la prueba de ui/quality/panel.py.",
        allow_module_level=True,
    )

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from domain.quality.entities import EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCategory  # noqa: E402
from infrastructure.database.quality_repositories import SqlAlchemyEvaluationRunRepository  # noqa: E402
from ui.quality.panel import QualityPanel  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _make_panel_with_project(app_context, qapp) -> tuple[QualityPanel, str]:
    project = app_context.project_service.create_project("Proyecto de prueba")
    panel = QualityPanel(app_context)
    panel.set_active_project(project.id)
    return panel, project.id


def _no_retrieval_item(code: str = "T1") -> EvaluationResultItem:
    return EvaluationResultItem(
        test_case_id="tc1", test_case_code=code, category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE,
    )


def _retrieval_item(rank, code: str = "T1") -> EvaluationResultItem:
    return EvaluationResultItem(
        test_case_id="tc1", test_case_code=code, category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE, retrieval_check_applicable=True, expected_source_rank=rank,
    )


def _save_complete_run(app_context, project_id: str, started_at, items) -> EvaluationRun:
    # Mismo criterio que tests/integration/test_quality_repositories.py:
    # se guarda directo por el repositorio real (misma base de datos que
    # usa app_context.quality_service, vía app_context.paths), sin pasar
    # por RunEvaluation.execute() -- correr una evaluación real de
    # extremo a extremo no permite fijar qué casos tienen fuente
    # esperada ni en qué posición apareció.
    repo = SqlAlchemyEvaluationRunRepository(app_context.paths)
    run = EvaluationRun(project_id=project_id, scope="completa", started_at=started_at, items=items)
    repo.save(run)
    return run


def test_regression_comparison_reports_no_metrics_when_neither_run_has_them(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    _save_complete_run(app_context, project_id, datetime(2026, 1, 1, tzinfo=timezone.utc), [_no_retrieval_item()])
    newest = _save_complete_run(
        app_context, project_id, datetime(2026, 1, 2, tzinfo=timezone.utc), [_no_retrieval_item()],
    )

    html = panel._render_regression_comparison(newest)

    assert "no tiene casos con fuente esperada declarada" in html
    assert "Ninguna de las dos" not in html


def test_regression_comparison_reports_no_comparable_previous_run(qapp, app_context):
    # El reporte real del usuario: la corrida más reciente sí calculó
    # Recall@3/MRR (4 casos, todos en el primer lugar), pero la corrida
    # "completa" anterior no tenía ningún caso con fuente esperada.
    panel, project_id = _make_panel_with_project(app_context, qapp)
    _save_complete_run(app_context, project_id, datetime(2026, 1, 1, tzinfo=timezone.utc), [_no_retrieval_item()])
    newest = _save_complete_run(
        app_context, project_id, datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )

    html = panel._render_regression_comparison(newest)

    assert "no tiene métricas Recall@3/MRR disponibles" in html
    assert "todavía no existe una base comparable" in html
    assert "Ninguna de las dos" not in html


def test_regression_comparison_shows_the_drop_when_both_runs_are_comparable(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    _save_complete_run(
        app_context, project_id, datetime(2026, 1, 1, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(4)],
    )
    newest = _save_complete_run(
        app_context, project_id, datetime(2026, 1, 2, tzinfo=timezone.utc),
        [_retrieval_item(rank=1, code=f"T{i}") for i in range(3)] + [_retrieval_item(rank=None, code="T3")],
    )

    html = panel._render_regression_comparison(newest)

    assert "75%" in html
    assert "100%" in html
