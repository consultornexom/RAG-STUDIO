"""Vocabularios que la UI necesita para construir formularios, sin
tener que importar domain directamente (ADR-001, sección 4: ui solo
depende de application)."""
from __future__ import annotations

from domain.documents.entities import (
    NON_FILE_SOURCE_TYPES, AccessLevel, SourceType, SourceValidationStatus, TERMINAL_VALIDATION_STATUSES,
)

SOURCE_TYPE_OPTIONS: list[str] = [t.value for t in SourceType]
ACCESS_LEVEL_OPTIONS: list[str] = [a.value for a in AccessLevel]
VALIDATION_STATUS_OPTIONS: list[str] = [s.value for s in SourceValidationStatus]

TERMINAL_VALIDATION_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in TERMINAL_VALIDATION_STATUSES)
"""Ronda 5 (hallazgo real de usuario): valores (no enums) de los
estados de validación sin transición de salida -- para que
ui.sources.panel pueda advertir antes de aplicar una de estas
transiciones, sin importar domain directamente (ADR-001, sección 4)."""

NON_FILE_SOURCE_TYPE_VALUES: frozenset[str] = frozenset(t.value for t in NON_FILE_SOURCE_TYPES)
"""Análisis de brechas dominio/UI a raíz de la nota de "valor múltiple"
del Manual del Usuario (sección 6.1): ui.sources.panel necesita saber
qué tipos de fuente NO corresponden a un archivo real (api,
base_de_datos) para no intentar calcular una huella de contenido
(content_hash) sobre una "ubicación" que en esos casos es una URL o
una cadena de conexión, no una ruta de archivo legible -- sin importar
domain directamente (ADR-001, sección 4)."""

IMAGE_SOURCE_TYPE_VALUE: str = SourceType.IMAGEN_NATIVA.value
"""Fase 4 de multimodalidad nativa (RAG 3): valor exacto (string) de
SourceType.IMAGEN_NATIVA -- para que la UI (filtro de archivo de
imagen y vista previa en miniatura al registrar una fuente, en
ui/sources/panel.py; decisión de indexar con IndexImageSource en vez
de IndexSource, en ui/ingestion/panel.py) pueda reconocer este tipo de
fuente sin importar domain.documents.entities.SourceType directamente
(ADR-001, sección 4), mismo criterio que el resto de este módulo."""
