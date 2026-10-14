"""Reproduce y verifica la corrección del hallazgo real de usuario
(Ronda 79, ver bitácora): en Diseño conversacional -> Variables, el
selector "Campo de metadatos ligado (opcional)" se quedaba mostrando
solo "— ninguno —" si el esquema de metadatos (o sus campos) se creaba
DESPUÉS de seleccionar el proyecto activo, en la misma sesión -- solo
se refrescaba llamando de nuevo a set_active_project (es decir, saliendo
y volviendo a entrar al proyecto).

Corregido con MetadataPanel.schema_changed (nueva señal, emitida al
final de _refresh_schema) conectada a
ConversationalPanel.refresh_metadata_fields en ui/projects/main_window.py
-- mismo patrón ya usado para SourcesPanel.sources_changed (Ronda 4,
punto 4b; Ronda 5)."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de metadata/conversational.",
                allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.conversational.panel import ConversationalPanel  # noqa: E402
from ui.metadata.panel import MetadataPanel  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _combo_texts(panel: ConversationalPanel) -> list[str]:
    combo = panel._variable_metadata_field
    return [combo.itemText(i) for i in range(combo.count())]


def test_metadata_field_combo_starts_with_only_none_option(qapp, app_context):
    project = app_context.project_service.create_project("Proyecto de prueba")
    metadata_panel = MetadataPanel(app_context)
    conversational_panel = ConversationalPanel(app_context)
    metadata_panel.schema_changed.connect(conversational_panel.refresh_metadata_fields)

    metadata_panel.set_active_project(project.id)
    conversational_panel.set_active_project(project.id)

    assert _combo_texts(conversational_panel) == ["— ninguno —"]


def test_metadata_field_combo_refreshes_when_schema_is_created_after_project_selection(qapp, app_context):
    # Reproduce exactamente el escenario reportado: proyecto ya
    # seleccionado en ambas pestañas (sin ningún esquema todavía), y
    # LUEGO se crea el esquema y se le agrega un campo -- sin volver a
    # seleccionar el proyecto ni recrear ningún panel.
    project = app_context.project_service.create_project("Proyecto de prueba")
    metadata_panel = MetadataPanel(app_context)
    conversational_panel = ConversationalPanel(app_context)
    metadata_panel.schema_changed.connect(conversational_panel.refresh_metadata_fields)

    metadata_panel.set_active_project(project.id)
    conversational_panel.set_active_project(project.id)
    assert _combo_texts(conversational_panel) == ["— ninguno —"]

    schema = app_context.metadata_service.create_schema(project.id)
    app_context.metadata_service.add_field_definition(
        project.id, schema.id, "campus", "Campus", "seleccion_multiple",
        filterable=True, inherited_by_chunks=True,
    )
    # _on_add_field real llama a _refresh_schema() al terminar; aquí se
    # invoca directamente porque el alta se hizo por servicio, no por
    # el diálogo de la interfaz.
    metadata_panel._refresh_schema()

    texts = _combo_texts(conversational_panel)
    assert texts == ["— ninguno —", "Campus (campus)"]
    conversational_panel._variable_metadata_field.setCurrentIndex(1)
    assert conversational_panel._variable_metadata_field.currentData() == "campus"


def test_metadata_field_combo_does_not_refresh_without_the_signal_connected(qapp, app_context):
    # Prueba de control: sin conectar schema_changed (como estaba antes
    # de esta ronda), el selector se queda desactualizado -- confirma
    # que el fixture anterior prueba la conexión real, no un efecto
    # secundario de otra cosa.
    project = app_context.project_service.create_project("Proyecto de prueba")
    metadata_panel = MetadataPanel(app_context)
    conversational_panel = ConversationalPanel(app_context)
    # A propósito: no se conecta metadata_panel.schema_changed aquí.

    metadata_panel.set_active_project(project.id)
    conversational_panel.set_active_project(project.id)

    schema = app_context.metadata_service.create_schema(project.id)
    app_context.metadata_service.add_field_definition(
        project.id, schema.id, "campus", "Campus", "seleccion_multiple",
    )
    metadata_panel._refresh_schema()

    assert _combo_texts(conversational_panel) == ["— ninguno —"]
