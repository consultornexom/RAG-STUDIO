"""Punto de entrada conveniente para la interfaz de escritorio.

Uso:
    python run_app.py

Requiere haber instalado el paquete en modo editable (pip install -e .)
y las dependencias (pip install -r requirements.txt, incluye la UI).
"""
import os
import sys
from pathlib import Path

# Bajo una sesión Wayland (la sesión por defecto en Ubuntu reciente al
# iniciar sesión con GNOME), el propio protocolo prohíbe que una
# aplicación posicione sus ventanas top-level -- no es configurable desde
# Qt ni desde este código: es una restricción de seguridad/UX del
# compositor. Por eso el splash con el logo y la ventana principal
# ignoraban por completo cualquier intento de centrado o de tamaño.
# Ubuntu incluye XWayland por defecto, así que forzamos el backend X11 de
# Qt (solo cuando detectamos Wayland y el usuario no fijó ya
# QT_QPA_PLATFORM por su cuenta) para que el centrado del splash y el
# maximizado de la ventana principal sí se respeten.
if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"


def main() -> int:
    try:
        from ui.app import main as ui_main
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from ui.app import main as ui_main

    return ui_main()


if __name__ == "__main__":
    raise SystemExit(main())