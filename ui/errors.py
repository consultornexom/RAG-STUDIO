"""Texto de error para los diálogos de la interfaz (Ronda 93, auditoría
del hallazgo "fallo sin categoría"): `str(exc)` es vacío para excepciones
sin mensaje (KeyError(), AssertionError()...) y el diálogo "Error" salía
en blanco, sin ningún rastro en el registro. Ahora el diálogo siempre dice
qué tipo de error ocurrió y la traza completa queda en logs/ragstudio.log."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def describe_error(exc: BaseException) -> str:
    logger.error("Error mostrado al usuario: %s: %s", type(exc).__name__, exc,
                 exc_info=(type(exc), exc, exc.__traceback__))
    mensaje = str(exc).strip()
    if not mensaje:
        return f"{type(exc).__name__} (sin mensaje). El detalle técnico quedó en logs/ragstudio.log."
    return mensaje
