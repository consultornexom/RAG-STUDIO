"""Ronda 102 (C4, autorizado por NEXOM): ajuste "Reranking en el agente" en
el Simulador y trazado de si se aplicó, con qué modelo, y de dónde salió
el orden de cada fragmento (C1)."""
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


def test_el_selector_guarda_y_muestra_el_ajuste_del_proyecto(qapp, app_context):
    project = app_context.project_service.create_project("Proyecto reranking")
    panel = ConversationalPanel(app_context)
    panel.set_active_project(project.id)
    assert panel._sim_reranking.currentData() is None  # automático por defecto
    panel._sim_reranking.setCurrentIndex(panel._sim_reranking.findData(False))
    panel._on_agent_reranking_changed()
    assert app_context.project_service.get_project(project.id).agent_reranking is False
    otro = ConversationalPanel(app_context)
    otro.set_active_project(project.id)
    assert otro._sim_reranking.currentData() is False


def test_el_reporte_indica_reranking_y_orden(qapp, app_context):
    panel = ConversationalPanel(app_context)
    chunk = Chunk(project_id="p", source_id="s", chunk_index=0, text="Acta de nacimiento", token_count=3)
    panel._pending_trace = SimulationTrace(
        query_text="requisitos", action=RuleActionType.RESPONDER, matched_intent_name="req", section_ordering=True,
        search_results=[SemanticSearchResult(chunk=chunk, score=0.5)],
        result_ordering=[ResultOrderingView(retrieval_rank=2, affinity=0.86, affinity_title="Requisitos de ingreso")],
        reranking_setting="automatico", reranking_applied=True, reranking_model="Xenova/ms-marco-MiniLM-L-6-v2",
    )
    panel._refresh_simulation_report()
    texto = panel._sim_report.toPlainText()
    assert "Reranking: aplicado — modelo Xenova/ms-marco-MiniLM-L-6-v2 (ajuste del proyecto: automático)" in texto
    assert "búsqueda #2; afinidad 0.86 con «Requisitos de ingreso»" in texto
