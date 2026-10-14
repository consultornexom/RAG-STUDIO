"""Punto de entrada de la interfaz de escritorio (PySide6).

No se ejecuta en el sandbox de construcción de este esqueleto (no hay
servidor gráfico ni bibliotecas del sistema como libEGL disponibles
allí); debe ejecutarse en la laptop/estación de trabajo objetivo, donde
Qt sí tiene sus dependencias nativas. Ver README para instrucciones.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from app.lifecycle import shutdown, start
from ui.projects.main_window import MainWindow
from ui.theme import HOJA_DE_ESTILOS

_LOGO_PATH = Path(__file__).resolve().parent / "LOGO.png"
_SPLASH_WIDTH = 480
_MIN_SPLASH_SECONDS = 1.0


def _show_splash(app: QApplication) -> QSplashScreen | None:
    """Muestra el logo de RAG STUDIO mientras la aplicación termina de arrancar.

    Se usa como pantalla de bienvenida: aparece de inmediato (antes de que
    ``app.lifecycle.start()`` corra migraciones y arme el contexto) y se
    cierra justo cuando la ventana principal ya está lista para mostrarse.
    Si el archivo del logo no existe o no puede leerse, se omite la
    pantalla de bienvenida sin interrumpir el arranque.
    """
    if not _LOGO_PATH.exists():
        return None
    pixmap = QPixmap(str(_LOGO_PATH))
    if pixmap.isNull():
        return None
    pixmap = pixmap.scaledToWidth(_SPLASH_WIDTH, Qt.TransformationMode.SmoothTransformation)
    splash = QSplashScreen(pixmap)
    splash.show()
    # El centrado debe pedirse DESPUÉS de mostrar la ventana: varios
    # gestores de ventanas en Linux ignoran move() sobre una ventana que
    # todavía no ha sido mapeada, y la dejan en la esquina superior
    # izquierda por defecto.
    app.processEvents()
    _center_on_primary_screen(splash)
    app.processEvents()
    return splash


def _center_on_primary_screen(widget) -> None:
    """Centra una ventana top-level (como el splash) en la pantalla principal."""
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    screen_geometry = screen.availableGeometry()
    widget_geometry = widget.frameGeometry()
    widget_geometry.moveCenter(screen_geometry.center())
    widget.move(widget_geometry.topLeft())


def main() -> int:
    app = QApplication(sys.argv)
    # Identidad visual consistente en toda la ventana (ver ui/theme.py
    # para el porqué y la paleta) -- una sola vez, antes de crear
    # cualquier widget, para que todo (incluido el splash) la herede.
    app.setStyleSheet(HOJA_DE_ESTILOS)
    splash = _show_splash(app)
    splash_started_at = time.monotonic()

    context = start()
    window = MainWindow(context)

    if splash is not None:
        # Con un arranque de por sí rápido (SQLite local), el bootstrap
        # completo puede tardar menos de lo que el ojo humano percibe, así
        # que el splash llegaba a cerrarse antes de pintarse una sola vez.
        # Se garantiza un mínimo de tiempo visible, bombeando el loop de
        # eventos (sin bloquear la UI) en vez de usar un sleep ciego.
        remaining = _MIN_SPLASH_SECONDS - (time.monotonic() - splash_started_at)
        deadline = time.monotonic() + remaining
        while time.monotonic() < deadline:
            app.processEvents()

    # Dos intentos anteriores (maximizar antes del primer show(), y
    # mostrar-normal-luego-maximizar, ambos con varias vueltas de
    # app.processEvents() intercaladas) dieron EXACTAMENTE el mismo
    # resultado roto: isMaximized()=True pero geometry=(0,0,1135,600) --
    # el tamaño natural de la ventana, no el de la pantalla. Que el
    # resultado sea bit por bit idéntico pase lo que pase con el orden
    # descarta una condición de carrera resoluble con más
    # processEvents(): esto es Mutter/XWayland necesitando una vuelta
    # real del *event loop en ejecución* (no una serie de bombeos
    # manuales antes de app.exec()) para completar el intercambio de
    # protocolo de maximizado. Por eso se muestra la ventana normal y se
    # difiere pedir el maximizado con QTimer.singleShot(): así la
    # petición ocurre igual que si un usuario la disparara ya con la
    # aplicación corriendo, no como parte de la ráfaga sincrónica de
    # arranque.
    window.show()

    def _finish_startup() -> None:
        window.showMaximized()
        context.logger.info(
            "Ventana principal: geometry=%s isMaximized=%s",
            window.geometry(), window.isMaximized(),
        )
        if splash is not None:
            splash.finish(window)

    QTimer.singleShot(300, _finish_startup)

    exit_code = app.exec()
    shutdown(context)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
