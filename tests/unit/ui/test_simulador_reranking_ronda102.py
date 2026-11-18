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


def test_ronda104b_el_reporte_incluye_los_datos_de_ejecucion(qapp, app_context):
    """Etapa 0: código, procedimiento, reranking efectivo (disponible,
    ajuste, aplicado) y texto exacto de búsqueda."""
    panel = ConversationalPanel(app_context)
    chunk = Chunk(project_id="p", source_id="s", chunk_index=0, text="texto", token_count=1)
    panel._pending_trace = SimulationTrace(
        query_text="q", action=RuleActionType.RESPONDER, search_results=[SemanticSearchResult(chunk=chunk, score=0.1)],
        reranking_setting="desactivado", reranking_applied=False, reranking_available=True,
        reranking_available_model="Xenova/ms-marco-MiniLM-L-6-v2", search_text="texto exacto",
    )
    panel._refresh_simulation_report()
    texto = panel._sim_report.toPlainText()
    assert "Procedimiento de recuperación: r105b" in texto
    assert ("Reranking: ajuste desactivado; no aplicado; modelo cargado (Xenova/ms-marco-MiniLM-L-6-v2) "
            "(no requerido)") in texto
    assert "Configuración efectiva en el Runtime: sin reranking — igual a la de esta simulación." in texto
    assert "Texto exacto de búsqueda: «texto exacto»" in texto
    assert "RAG Studio " in texto and "huella del código" in texto


def test_ronda105b_el_selector_muestra_la_configuracion_efectiva(qapp, app_context):
    project = app_context.project_service.create_project("Proyecto efectiva")
    panel = ConversationalPanel(app_context)
    panel.set_active_project(project.id)
    assert panel._sim_reranking.currentText().startswith("Automático (predeterminado): sin reranking")
    assert "SIN reranking" in panel._sim_reranking_effective.text()
    panel._sim_reranking.setCurrentIndex(panel._sim_reranking.findData(True))
    import ui.conversational.panel as modulo
    original = modulo.QMessageBox.information
    modulo.QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        panel._on_agent_reranking_changed()
    finally:
        modulo.QMessageBox.information = original
    assert "CON reranking" in panel._sim_reranking_effective.text()
    assert app_context.project_service.get_project(project.id).agent_reranking is True
