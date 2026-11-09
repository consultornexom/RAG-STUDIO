"""Ronda 97 (hallazgo real de NEXOM, AGENTE UDL, con capturas): en
Metadatos > Valores por fuente, un campo `seleccion_multiple` con catálogo y
"Permite varios valores" mostraba un selector de UNA sola entrada; guardar
torres_landa sustituía a hilario_medina. Prueba de aceptación en la
interfaz real (Qt offscreen)."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}).", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from domain.documents.entities import SourceType  # noqa: E402
from ui.metadata import panel as panel_module  # noqa: E402
from ui.metadata.panel import MetadataPanel  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def escenario(app_context):
    ctx = app_context
    project = ctx.project_service.create_project("AGENTE UDL prueba")
    meta = ctx.metadata_service
    schema = meta.create_schema(project.id)
    nivel = meta.create_catalog(project.id, "nivel")
    meta.add_catalog_entry(project.id, nivel.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(project.id, schema.id, "nivel_academico", "Nivel académico", "seleccion_unica",
                              catalog_id=nivel.id)
    campus = meta.create_catalog(project.id, "campus_udl")
    meta.add_catalog_entry(project.id, campus.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(project.id, campus.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(project.id, schema.id, "campus", "Campus o plantel", "seleccion_multiple",
                              multiple=True, filterable=True, inherited_by_chunks=True, catalog_id=campus.id)
    req = ctx.document_service.register_source(project.id, "requisitos_ingreso.md", SourceType.MARKDOWN)
    becas = ctx.document_service.register_source(project.id, "becas.md", SourceType.MARKDOWN)
    return ctx, project.id, schema.id, req.id, becas.id


def _abrir(ctx, pid, source_id, field_id="campus") -> MetadataPanel:
    panel = MetadataPanel(ctx)
    panel.set_active_project(pid)
    panel._value_source_selector.setCurrentIndex(panel._value_source_selector.findData(source_id))
    panel._value_field_selector.setCurrentIndex(panel._value_field_selector.findData(field_id))
    return panel


def _marcar(panel, codigos):
    lista = panel._value_input_catalog_multi
    for i in range(lista.count()):
        item = lista.item(i)
        item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in codigos
                           else Qt.CheckState.Unchecked)


def _filas(panel):
    lista = panel._current_values_list
    return [lista.item(i).text() for i in range(lista.count())]


def _valor(ctx, pid, src, field_id="campus"):
    return {v.field_id: v.value for v in ctx.metadata_service.list_source_metadata_values(pid, src)}.get(field_id)


def test_campo_multivalor_muestra_lista_con_casillas(qapp, escenario):
    ctx, pid, _sid, req, _ = escenario
    panel = _abrir(ctx, pid, req)
    assert not panel._value_input_catalog_multi.isHidden()
    assert panel._value_input_catalog.isHidden()
    assert panel._value_input_catalog_multi.count() == 2
    assert not panel._value_bulk_add_mode.isHidden()
    # Un campo de un solo valor conserva el selector de siempre.
    panel._value_field_selector.setCurrentIndex(panel._value_field_selector.findData("nivel_academico"))
    assert not panel._value_input_catalog.isHidden() and panel._value_input_catalog_multi.isHidden()
    assert panel._value_bulk_add_mode.isHidden()


def test_aceptacion_ambos_planteles_se_guardan_y_persisten_al_reabrir(qapp, escenario):
    ctx, pid, _sid, req, _ = escenario
    panel = _abrir(ctx, pid, req)
    _marcar(panel, ["hilario_medina", "torres_landa"])
    panel._on_save_source_value()
    assert _valor(ctx, pid, req) == "hilario_medina|torres_landa"

    reabierto = _abrir(ctx, pid, req)
    assert reabierto._checked_catalog_codes() == ["hilario_medina", "torres_landa"]
    filas = _filas(reabierto)
    assert any("hilario_medina — Hilario Medina" in f for f in filas)
    assert any("torres_landa — Torres Landa" in f for f in filas)


def test_guardar_otro_plantel_ya_no_sustituye_al_anterior(qapp, escenario):
    """Flujo de la captura: se guarda hilario_medina y luego se marca también torres_landa."""
    ctx, pid, _sid, req, _ = escenario
    panel = _abrir(ctx, pid, req)
    _marcar(panel, ["hilario_medina"])
    panel._on_save_source_value()
    # Al recargar, hilario_medina sigue marcado; el usuario marca torres_landa además.
    assert panel._checked_catalog_codes() == ["hilario_medina"]
    lista = panel._value_input_catalog_multi
    lista.item(1).setCheckState(Qt.CheckState.Checked)
    panel._on_save_source_value()
    assert _valor(ctx, pid, req) == "hilario_medina|torres_landa"


def test_desmarcar_y_guardar_modifica_y_quitar_valor_borra_solo_uno(qapp, escenario, monkeypatch):
    ctx, pid, sid, req, _ = escenario
    ctx.metadata_service.set_source_metadata_value(pid, sid, req, "campus", ["hilario_medina", "torres_landa"])
    panel = _abrir(ctx, pid, req)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

    # Quitar valor sobre la fila de torres_landa: hilario_medina se conserva.
    lista = panel._current_values_list
    fila = next(i for i in range(lista.count()) if "torres_landa" in lista.item(i).text())
    lista.setCurrentRow(fila)
    panel._on_delete_source_value()
    assert _valor(ctx, pid, req) == "hilario_medina"
    assert panel._checked_catalog_codes() == ["hilario_medina"]

    # Volver a marcar ambos, y luego desmarcar hilario_medina: queda solo torres_landa.
    _marcar(panel, ["hilario_medina", "torres_landa"])
    panel._on_save_source_value()
    _marcar(panel, ["torres_landa"])
    panel._on_save_source_value()
    assert _valor(ctx, pid, req) == "torres_landa"


def test_sin_casillas_marcadas_no_borra_en_silencio(qapp, escenario, monkeypatch):
    ctx, pid, sid, req, _ = escenario
    ctx.metadata_service.set_source_metadata_value(pid, sid, req, "campus", ["hilario_medina"])
    panel = _abrir(ctx, pid, req)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[1]))
    _marcar(panel, [])
    panel._on_save_source_value()
    assert avisos == ["Sin valores marcados"]
    assert _valor(ctx, pid, req) == "hilario_medina"


def _aplicar_a(monkeypatch, fuentes):
    class _Dialogo:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.Accepted

        def selected_source_ids(self):
            return fuentes

    monkeypatch.setattr(panel_module, "_MultiSourceSelectionDialog", _Dialogo)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)


def test_asignacion_masiva_agrega_por_defecto_y_conserva_lo_existente(qapp, escenario, monkeypatch):
    ctx, pid, sid, req, becas = escenario
    ctx.metadata_service.set_source_metadata_value(pid, sid, req, "campus", ["hilario_medina"])
    panel = _abrir(ctx, pid, req)
    _aplicar_a(monkeypatch, [req, becas])
    _marcar(panel, ["torres_landa"])
    assert panel._value_bulk_add_mode.isChecked()
    panel._on_apply_value_to_multiple_sources()
    assert _valor(ctx, pid, req) == "hilario_medina|torres_landa"
    assert _valor(ctx, pid, becas) == "torres_landa"


def test_asignacion_masiva_reemplazar_con_varios_valores(qapp, escenario, monkeypatch):
    ctx, pid, sid, req, becas = escenario
    ctx.metadata_service.set_source_metadata_value(pid, sid, becas, "campus", ["torres_landa"])
    panel = _abrir(ctx, pid, req)
    _aplicar_a(monkeypatch, [req, becas])
    _marcar(panel, ["hilario_medina", "torres_landa"])
    panel._value_bulk_add_mode.setChecked(False)
    panel._on_apply_value_to_multiple_sources()
    assert _valor(ctx, pid, req) == _valor(ctx, pid, becas) == "hilario_medina|torres_landa"
