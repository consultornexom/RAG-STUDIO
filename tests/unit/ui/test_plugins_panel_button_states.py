"""Pruebas de la lógica de habilitación de botones de PluginsPanel
según la selección de la lista de complementos.

Auditoría posterior a la Ronda 77 (hallazgo real de usuario, ver
bitácora): "Activar/Desactivar seleccionado", "Validar seleccionado",
"Editar…" y "Eliminar" quedaban pintados como disponibles aunque no
hubiera ningún complemento seleccionado -- pulsarlos entonces retornaba
en silencio (`_selected_plugin() is None`), sin ningún aviso. Corregido
con `_apply_button_states()`, mismo patrón que ProjectsPanel (ver
test_projects_panel_button_states.py) y que ya usaba correctamente
ui/monitoring/panel.py."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de ui/plugins/panel.py.",
                allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from domain.plugins.entities import PluginKind  # noqa: E402
from ui.plugins.panel import PluginsPanel  # noqa: E402

_BOTONES_DEPENDIENTES_DE_SELECCION = ("_btn_toggle", "_btn_validate", "_btn_edit", "_btn_delete")


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _estan_habilitados(panel: PluginsPanel) -> bool:
    estados = {getattr(panel, nombre).isEnabled() for nombre in _BOTONES_DEPENDIENTES_DE_SELECCION}
    assert len(estados) == 1, "los cuatro botones deberían compartir el mismo estado habilitado/deshabilitado"
    return estados.pop()


def test_buttons_start_disabled_when_there_are_no_plugins_yet(qapp, app_context):
    panel = PluginsPanel(app_context)
    assert _estan_habilitados(panel) is False
    # "Registrar complemento" no depende de ninguna selección -- debe
    # seguir disponible.
    assert panel._btn_register.isEnabled() is True


def test_buttons_enable_once_a_plugin_is_selected(qapp, app_context):
    panel = PluginsPanel(app_context)
    app_context.plugin_service.register_plugin(PluginKind.PLANTILLA, "plantilla_prueba", "Plantilla de prueba")
    panel._refresh_plugins()
    assert _estan_habilitados(panel) is False  # refrescar no selecciona nada por sí solo

    panel._plugin_list.setCurrentRow(0)
    assert _estan_habilitados(panel) is True


def test_buttons_disable_again_after_clearing_the_selection(qapp, app_context):
    panel = PluginsPanel(app_context)
    app_context.plugin_service.register_plugin(PluginKind.PLANTILLA, "plantilla_prueba", "Plantilla de prueba")
    panel._refresh_plugins()
    panel._plugin_list.setCurrentRow(0)
    assert _estan_habilitados(panel) is True

    panel._plugin_list.setCurrentRow(-1)
    assert _estan_habilitados(panel) is False
