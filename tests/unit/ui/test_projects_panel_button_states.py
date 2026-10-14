"""Pruebas de la lógica de habilitación de botones de ProjectsPanel
según la selección de la lista de proyectos.

Auditoría posterior a la Ronda 77 (hallazgo real de usuario, ver
bitácora): "Editar nombre…", "Editar detalles…", "Cambiar estado…",
"Archivar", "Eliminar" y "Exportar proyecto (.agentproj)…" quedaban
pintados como disponibles aunque no hubiera ningún proyecto
seleccionado -- pulsarlos entonces retornaba en silencio
(`_selected_project_id() is None`), sin ningún aviso. Corregido con
`_apply_button_states()`, siguiendo el mismo patrón que ya usaba
correctamente `ui/monitoring/panel.py`.

Construye widgets reales de PySide6 sobre `QT_QPA_PLATFORM=offscreen`
(mismo mecanismo que ya usa tests/smoke/test_ui_construction.py, que sí
corre en este entorno) -- a diferencia de tests/unit/ui/test_theme.py,
que solo prueba lógica pura sin construir widgets, aquí sí hace falta
un widget real para leer `isEnabled()`."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de ui/projects/panel.py.",
                allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.projects.panel import ProjectsPanel  # noqa: E402

_BOTONES_DEPENDIENTES_DE_SELECCION = (
    "_btn_edit_name", "_btn_edit_details", "_btn_change_status",
    "_btn_archive", "_btn_delete", "_btn_export",
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _estan_habilitados(panel: ProjectsPanel) -> bool:
    estados = {getattr(panel, nombre).isEnabled() for nombre in _BOTONES_DEPENDIENTES_DE_SELECCION}
    assert len(estados) == 1, "los seis botones deberían compartir el mismo estado habilitado/deshabilitado"
    return estados.pop()


def test_buttons_start_disabled_when_there_are_no_projects_yet(qapp, app_context):
    panel = ProjectsPanel(app_context)
    assert _estan_habilitados(panel) is False
    # "Nuevo proyecto" e "Importar proyecto (.agentproj)…" no dependen de
    # ninguna selección -- deben seguir disponibles.
    assert panel._btn_new.isEnabled() is True
    assert panel._btn_import.isEnabled() is True


def test_buttons_enable_once_a_project_is_selected(qapp, app_context):
    panel = ProjectsPanel(app_context)
    project = app_context.project_service.create_project("Proyecto de prueba")
    panel._refresh_projects(select_project_id=project.id)
    assert _estan_habilitados(panel) is True


def test_buttons_disable_again_after_clearing_the_selection(qapp, app_context):
    panel = ProjectsPanel(app_context)
    project = app_context.project_service.create_project("Proyecto de prueba")
    panel._refresh_projects(select_project_id=project.id)
    assert _estan_habilitados(panel) is True

    panel._project_list.setCurrentItem(None)
    assert _estan_habilitados(panel) is False


def test_import_button_tooltip_points_to_the_correct_flow_for_rag_content_folders(qapp, app_context):
    # Verificación directa del hallazgo real de usuario: el tooltip debe
    # dejar explícito que este botón NUNCA acepta una carpeta, y cruzar
    # hacia el botón correcto de la pestaña Fuentes.
    panel = ProjectsPanel(app_context)
    tooltip = panel._btn_import.toolTip()
    assert "nunca una carpeta" in tooltip
    assert "Importar carpeta de RAG CONTENT" in tooltip
