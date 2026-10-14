"""Prueba de humo de la UI. Se omite automáticamente si el entorno no
tiene las bibliotecas nativas de Qt disponibles (por ejemplo, este
sandbox de construcción no tiene libEGL y no hay servidor gráfico).
En una laptop real con PySide6 instalado normalmente, esta prueba sí
se ejecuta y construye la ventana principal.
"""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(f"Qt no disponible en este entorno ({exc}); se omite la prueba de UI.",
                allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_main_window_constructs_without_crashing(app_context):
    from PySide6.QtWidgets import QApplication

    from ui.projects.main_window import MainWindow
    from ui.theme import HOJA_DE_ESTILOS

    app = QApplication.instance() or QApplication([])  # asegura que exista el singleton de Qt
    # Se aplica la misma hoja de estilos que ui/app.py aplica en el
    # arranque real (agregado en la auditoría de madurez ronda 5): antes
    # esta prueba construía la ventana sin ningún QSS, así que un error
    # de sintaxis en HOJA_DE_ESTILOS no lo hubiera detectado nunca.
    app.setStyleSheet(HOJA_DE_ESTILOS)
    window = MainWindow(app_context)
    assert window.windowTitle().startswith("RAG STUDIO")
    window.close()
