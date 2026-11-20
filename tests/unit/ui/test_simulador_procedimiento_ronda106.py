"""Ronda 106 (autorizada por NEXOM): selector «Procedimiento de recuperación»
del Simulador y trazado de referencias (r106)."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}).", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from application.conversational.queries.simulate_conversation import (  # noqa: E402
    ResultOrderingView, SimulationTrace,
)
from application.rag.queries.semantic_search import SemanticSearchResult  # noqa: E402
from domain.conversational.entities import RuleActionType  # noqa: E402
from domain.ingestion.entities import Chunk  # noqa: E402
from ui.conversational.panel import ConversationalPanel  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_selector_solo_ofrece_los_dos_procedimientos_completos(qapp, app_context):
    panel = ConversationalPanel(app_context)
    valores = [panel._sim_procedure.itemData(i) for i in range(panel._sim_procedure.count())]
    assert valores == ["r106", "r105b"]  # nunca V sin R


def test_proyecto_nuevo_muestra_r106_y_el_cambio_se_guarda(qapp, app_context):
    project = app_context.project_service.create_project("Proyecto r106")
    panel = ConversationalPanel(app_context)
    panel.set_active_project(project.id)
    assert panel._sim_procedure.currentData() == "r106"
    panel._sim_procedure.setCurrentIndex(panel._sim_procedure.findData("r105b"))
    panel._on_retrieval_procedure_changed()
    assert app_context.project_service.get_retrieval_procedure(project.id) == ("r105b", True)
    otro = ConversationalPanel(app_context)
    otro.set_active_project(project.id)
    assert otro._sim_procedure.currentData() == "r105b"


def test_el_reporte_indica_procedimiento_y_referencia(qapp, app_context):
    panel = ConversationalPanel(app_context)
    chunk = Chunk(project_id="p", source_id="s", chunk_index=0, text="Acta de nacimiento", token_count=3)
    panel._pending_trace = SimulationTrace(
        query_text="documentos", action=RuleActionType.RESPONDER, matched_intent_name="req", section_ordering=True,
        search_results=[SemanticSearchResult(chunk=chunk, score=0.5)],
        result_ordering=[ResultOrderingView(
            retrieval_rank=13, affinity=0.37, affinity_title="Requisitos de ingreso — Bachillerato UDL",
            referenced_from=["c-puente"], referenced_from_sources=["bachillerato_torres_landa.md"],
        )],
        retrieval_pipeline="r106", ambiguous_references=["requisitos_ingreso.md"],
    )
    panel._refresh_simulation_report()
    texto = panel._sim_report.toPlainText()
    assert "traído por referencia desde bachillerato_torres_landa.md" in texto
    assert "Procedimiento de recuperación: r106" in texto
    assert "Referencias ambiguas (no resueltas): requisitos_ingreso.md" in texto
