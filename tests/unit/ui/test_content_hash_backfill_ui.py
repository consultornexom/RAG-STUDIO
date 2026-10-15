"""RAG-INC-01 — acción "Completar huellas de contenido…" de la pestaña Fuentes
(decisión NEXOM sobre INC01-R1): textos del resumen (sin Qt) y panel real."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import pytest

from domain.documents.content_hash_backfill import (
    BackfillStatus,
    ContentHashBackfillReport,
    SourceBackfillResult,
)
from ui.sources import content_hash_backfill_summary as backfill_ui


def _r(sid, estado):
    return SourceBackfillResult(source_id=sid, title=f"Título {sid}", source_type="pdf", lineage_id="L", status=estado)


def test_resumen_muestra_conteos_revision_e_informe():
    informe = ContentHashBackfillReport(
        project_id="p", started_at=datetime.now(timezone.utc), missing_before=3, missing_after=2,
        report_path="/x/reports/content_hash_backfill.json",
        results=[_r("a", BackfillStatus.RELLENADA), _r("b", BackfillStatus.COLISION_MISMO_LINAJE),
                 _r("c", BackfillStatus.SIN_COPIA_ORIGINAL)],
    )
    texto = backfill_ui.resumen(informe)
    assert "3 antes → 2 después" in texto
    assert "Completadas: 1" in texto
    assert "Requieren revisión" in texto and "Título b (colisión_mismo_linaje)" in texto
    assert "/x/reports/content_hash_backfill.json" in texto
    assert "instantánea nueva" not in texto  # aún faltan


def test_resumen_completo_recuerda_publicar_instantanea():
    informe = ContentHashBackfillReport(
        project_id="p", started_at=datetime.now(timezone.utc), missing_before=1, missing_after=0,
        results=[_r("a", BackfillStatus.RELLENADA)],
    )
    texto = backfill_ui.resumen(informe)
    assert "instantánea nueva" in texto and "No se pudo guardar el informe" in texto


def test_confirmacion_explica_reglas():
    assert "sources/original" in backfill_ui.CONFIRMACION
    assert "Nunca se modifica una huella existente" in backfill_ui.CONFIRMACION


# ------------------------------------------------------------ panel real

def _qt():
    try:
        import PySide6.QtWidgets  # noqa: F401
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"Qt no disponible ({exc})")
    return QApplication.instance() or QApplication([])


def test_panel_ejecuta_backfill_solo_tras_confirmar(app_context, tmp_path, monkeypatch):
    _qt()
    from PySide6.QtWidgets import QMessageBox

    from domain.documents.entities import SourceType
    from ui.sources.panel import SourcesPanel

    pid = app_context.project_service.create_project("P").id
    archivo = tmp_path / "doc.pdf"
    archivo.write_bytes(b"contenido")
    fuente = app_context.document_service.register_source(pid, "Doc", SourceType.PDF, location=str(archivo))

    panel = SourcesPanel(app_context)
    panel.set_active_project(pid)
    assert panel._btn_backfill_hashes.isEnabled()
    mostrados: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda _p, _t, texto: mostrados.append(texto)))
    monkeypatch.setattr(panel, "_report_error", lambda exc: pytest.fail(f"error inesperado: {exc}"))

    def _hash():
        con = sqlite3.connect(app_context.paths.project_db_path(pid))
        try:
            return con.execute("SELECT content_hash FROM source WHERE id = ?", (fuente.id,)).fetchone()[0]
        finally:
            con.close()

    # Cancelar: no se ejecuta nada.
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Cancel))
    panel._on_backfill_content_hashes()
    assert _hash() is None and mostrados == []

    # Confirmar: se completa y se muestra el resumen.
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    panel._on_backfill_content_hashes()
    assert _hash() is not None
    assert "1 antes → 0 después" in mostrados[0] and "reports" in mostrados[0]


def test_boton_deshabilitado_sin_proyecto(app_context):
    _qt()
    from ui.sources.panel import SourcesPanel

    panel = SourcesPanel(app_context)
    assert not panel._btn_backfill_hashes.isEnabled()
