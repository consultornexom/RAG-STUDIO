"""Ronda 99 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
"Ver detalle del fragmento" en Ingesta > Fragmentación (Qt offscreen)."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}).", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from domain.documents.entities import SourceType  # noqa: E402
from domain.ingestion.entities import FragmentationStrategy  # noqa: E402
from ui.ingestion.chunk_detail_dialog import format_chunk_detail  # noqa: E402
from ui.ingestion.panel import IngestionPanel  # noqa: E402

TEXTO = (
    "# Bachillerato — Plantel Torres Landa\n\n"
    "## Área Económico-Administrativa y Humanidades\n\n"
    "### 5.º semestre\n* Geografía\n* Economía I <b>no es HTML</b> & \"comillas\"\n\n"
    "## Área Físico-Matemática y Químico-Biológicas\n\n"
    "### 5.º semestre\n* Cálculo diferencial\n"
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, app_context, tmp_path):
    ctx = app_context
    pid = ctx.project_service.create_project("LOTE01").id
    meta = ctx.metadata_service
    sid = meta.create_schema(pid).id
    cat = meta.create_catalog(pid, "campus_udl")
    for code, label in (("hilario_medina", "Hilario Medina"), ("torres_landa", "Torres Landa")):
        meta.add_catalog_entry(pid, cat.id, code, label)
    meta.add_field_definition(pid, sid, "campus", "Campus o plantel", "seleccion_multiple", multiple=True,
                              inherited_by_chunks=True, catalog_id=cat.id)
    ctx.ingestion_service.set_fragmentation_policy(pid, "default", strategy=FragmentationStrategy.POR_ENCABEZADO)
    ruta = tmp_path / "bachillerato_torres_landa.md"
    ruta.write_text(TEXTO, encoding="utf-8")
    src = ctx.document_service.register_source(pid, "bachillerato_torres_landa.md", SourceType.MARKDOWN,
                                               location=str(ruta)).id
    meta.set_source_metadata_value(pid, sid, src, "campus", ["hilario_medina", "torres_landa"])
    ctx.ingestion_service.extract_source_text(pid, src)
    ctx.ingestion_service.fragment_source(pid, src, schema_id=sid)
    p = IngestionPanel(ctx)
    p.set_active_project(pid)
    p.set_active_source(src)
    return p, ctx, pid, src


def _fila(panel, titulo, n=0):
    lista = panel._chunk_list
    filas = [i for i in range(lista.count()) if f"sección: {titulo}" in lista.item(i).text()]
    return filas[n]


def test_doble_clic_abre_el_detalle_con_el_texto_integro_en_texto_plano(panel):
    p, ctx, pid, src = panel
    p._chunk_list.setCurrentRow(_fila(p, "5.º semestre", 0))
    dialog = p._on_chunk_detail()
    assert dialog is not None
    chunk_id = p._chunk_list.currentItem().data(Qt.ItemDataRole.UserRole)
    guardado = next(c for c in ctx.ingestion_service.list_chunks(pid, src) if c.id == chunk_id)
    assert dialog._texto.toPlainText() == guardado.text
    assert "<b>no es HTML</b>" in dialog._texto.toPlainText()  # literal, no interpretado
    assert dialog._texto.isReadOnly() and dialog._metadatos.isReadOnly()
    assert "    • hilario_medina\n    • torres_landa" in dialog._metadatos.toPlainText()
    assert "representación original: hilario_medina|torres_landa" in dialog._metadatos.toPlainText()
    contexto = dialog._contexto.toPlainText()
    assert "## Área Económico-Administrativa y Humanidades" in contexto
    assert "NO contiene estos encabezados superiores" in contexto
    dialog.copy_text()
    assert QGuiApplication.clipboard().text() == guardado.text
    dialog.close()


def test_los_dos_quinto_semestre_muestran_areas_distintas(panel):
    p, *_ = panel
    rutas = []
    for n in (0, 1):
        p._chunk_list.setCurrentRow(_fila(p, "5.º semestre", n))
        dialog = p._on_chunk_detail()
        rutas.append(dialog._contexto.toPlainText())
        dialog.close()
    assert "Económico-Administrativa" in rutas[0] and "Físico-Matemática" not in rutas[0]
    assert "Físico-Matemática" in rutas[1] and "Económico-Administrativa" not in rutas[1]


def test_navegacion_anterior_siguiente(panel):
    p, *_ = panel
    p._chunk_list.setCurrentRow(_fila(p, "5.º semestre", 0))
    dialog = p._on_chunk_detail()
    assert "Fragmento anterior: [" in dialog._propiedades.toPlainText()
    dialog._btn_anterior.click()
    assert "Área Económico-Administrativa y Humanidades" in dialog._encabezado.text()
    assert "Indexación: no — Solo contiene su encabezado" in dialog._propiedades.toPlainText()
    dialog._btn_siguiente.click()
    assert "«5.º semestre»" in dialog._encabezado.text()
    assert not dialog._btn_padre.isEnabled()
    dialog.close()


def test_sin_fragmento_seleccionado_avisa(panel, monkeypatch):
    p, *_ = panel
    from PySide6.QtWidgets import QMessageBox
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[1]))
    p._chunk_list.setCurrentRow(-1)
    assert p._on_chunk_detail() is None
    assert avisos == ["Elige un fragmento"]


def test_formato_de_fragmento_sin_metadatos_ni_encabezados(panel):
    p, ctx, pid, src = panel
    detail = ctx.ingestion_service.get_chunk_detail(pid, src, ctx.ingestion_service.list_chunks(pid, src)[0].id)
    detail.inherited_metadata = []
    detail.heading_context_status = "no_aplica"
    detail.heading_path = []
    secciones = format_chunk_detail(detail)
    assert "no hereda metadatos" in secciones["metadatos"]
    assert "no proviene de un encabezado" in secciones["contexto"]
