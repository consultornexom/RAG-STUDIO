"""Regresion real de usuario (Auditoria 2026-09-02, evidencia
RAG_STUDIO_01.mov + RAG_STUDIO_01_consola.txt): abrir la pestaña
"Metadatos" > "Valores por fuente" de un proyecto que todavia no tiene
un esquema de metadatos activo (o que lo perdio) tumbaba la aplicacion
entera con `domain.metadata.exceptions.MetadataDomainError: No hay
esquema de metadatos activo para '<id>'`, sin ningun try/except que lo
capturara -- ver el fix en `ui/metadata/panel.py::
MetadataPanel._fields_for_active_value_source()`.

Se omite automaticamente si el entorno no tiene las bibliotecas nativas
de Qt disponibles, mismo criterio que tests/smoke/test_ui_construction.py."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de UI.", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_seleccionar_una_fuente_sin_esquema_activo_no_revienta_la_app(app_context):
    from PySide6.QtWidgets import QApplication

    from domain.documents.entities import SourceType
    from ui.metadata.panel import MetadataPanel

    QApplication.instance() or QApplication([])

    project = app_context.project_service.create_project("Proyecto sin esquema")
    # A proposito: se registra una fuente pero NUNCA se crea un esquema
    # de metadatos para el proyecto (MetadataService.create_schema) --
    # el escenario real que hizo fallar `list_applicable_fields()`.
    app_context.document_service.register_source(project.id, "documento_de_prueba.pdf", SourceType.PDF)

    panel = MetadataPanel(app_context)
    # Antes del fix, esta linea por si sola ya lanzaba MetadataDomainError
    # sin capturar (set_active_project -> _refresh_value_source_selector
    # -> _on_value_source_changed -> _refresh_value_field_selector ->
    # _fields_for_active_value_source -> list_applicable_fields).
    panel.set_active_project(project.id)

    # Sin esquema activo, el selector de campos queda vacio -- pero la
    # aplicacion sigue viva y la pestaña "Valores por fuente" se puede
    # seguir usando con normalidad.
    assert panel._value_field_selector.count() == 0
    panel.close()
