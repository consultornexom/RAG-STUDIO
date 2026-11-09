"""Ronda 98 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
la pestaña Pipeline ya no tiene un selector global de document_type_code
(inducía a pensar que se usaban las políticas de cada fuente), ofrece una
vista previa sin efectos y el reporte muestra la política aplicada y el
motivo por fuente."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}).", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from domain.documents.entities import SourceType  # noqa: E402
from domain.ingestion.entities import FragmentationStrategy  # noqa: E402
from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus  # noqa: E402
from ui.ingestion.panel import IngestionPanel  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def proyecto(app_context, tmp_path):
    pid = app_context.project_service.create_project("LOTE01").id
    app_context.ingestion_service.set_fragmentation_policy(pid, "programa_academico",
                                                           strategy=FragmentationStrategy.POR_ENCABEZADO)
    ids = {}
    for nombre, tipo in (("programa", "programa_academico"), ("calendario", "informacion_academica")):
        ruta = tmp_path / f"{nombre}.md"
        ruta.write_text(f"# {nombre}\ntexto de {nombre}\n", encoding="utf-8")
        ids[nombre] = app_context.document_service.register_source(
            pid, f"{nombre}.md", SourceType.MARKDOWN, location=str(ruta), document_type_code=tipo,
        ).id
    return pid, ids


def test_no_hay_selector_global_y_la_vista_previa_muestra_politica_por_fuente(qapp, app_context, proyecto):
    pid, _ = proyecto
    panel = IngestionPanel(app_context)
    panel.set_active_project(pid)
    assert not hasattr(panel, "_pipeline_document_type_code")
    assert "política de su tipo de documento" in panel._pipeline_policy_note.text()
    panel._on_preview_pipeline()
    texto = panel._pipeline_report.toPlainText()
    assert "Vista previa (no se procesó nada)" in texto
    assert "tipo: programa_academico · política: programa_academico (por_encabezado" in texto
    assert "tipo: informacion_academica · política: interna de RAG Studio" in texto
    assert app_context.pipeline_service.list_runs(pid) == []


def test_reporte_muestra_politica_aplicada_y_motivo(qapp, app_context, proyecto):
    pid, ids = proyecto
    panel = IngestionPanel(app_context)
    panel.set_active_project(pid)
    panel._pending_pipeline_run = PipelineRun(project_id=pid, status=PipelineRunStatus.COMPLETO, items=[
        PipelineRunItem(source_id=ids["programa"], source_title="programa.md", status=PipelineItemStatus.OMITIDO,
                        document_type_code="programa_academico", policy_document_type_code="programa_academico",
                        policy_origin="especifica", policy_strategy="por_encabezado",
                        reason="Sin cambios: mismo archivo, misma política y mismos metadatos heredados."),
        PipelineRunItem(source_id=ids["calendario"], source_title="calendario.md", status=PipelineItemStatus.EXITOSO,
                        chunks_indexed=1, document_type_code="informacion_academica",
                        policy_document_type_code="default", policy_origin="default_proyecto",
                        policy_strategy="documento_completo", reason="Cambió la política de fragmentación aplicable."),
    ])
    panel._refresh_pipeline_report()
    texto = panel._pipeline_report.toPlainText()
    assert "tipo: programa_academico · política: programa_academico (por_encabezado, política de su tipo)" in texto
    assert "política: default (documento_completo, política default del proyecto)" in texto
    assert "motivo: Cambió la política de fragmentación aplicable." in texto


def test_fragmentacion_preselecciona_el_tipo_de_la_fuente_activa(qapp, app_context, proyecto):
    pid, ids = proyecto
    panel = IngestionPanel(app_context)
    panel.set_active_project(pid)
    panel.set_active_source(ids["calendario"])
    assert panel._document_type_code.currentText() == "informacion_academica"
    panel.set_active_source(ids["programa"])
    assert panel._document_type_code.currentText() == "programa_academico"
