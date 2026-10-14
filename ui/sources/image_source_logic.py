"""Lógica pura (sin Qt) del alta de fuentes tipo Imagen -- Fase 4 de
multimodalidad nativa (RAG 3, ver docs proyecto/RAG_STUDIO_Diseno_
Ejecutable_RAG3_Multimodalidad.docx, sección 3.6).

Se extrae de `_RegisterSourceDialog` (ui/sources/panel.py) siguiendo el
mismo patrón ya establecido en este proyecto para separar decisiones
puras de los widgets Qt que las usan (ver ui/conversational/parsing.py,
ui/ingestion/search_highlighting.py, ui/release/gate_status_logic.py):
la UI de escritorio solo se valida manualmente (ver pyproject.toml,
[tool.coverage.run]), así que cualquier lógica con ramas reales debe
vivir aquí para poder probarse con pytest normal, sin necesitar
pytest-qt (no instalado en este proyecto).
"""
from __future__ import annotations

from typing import Optional

from application.documents.options import IMAGE_SOURCE_TYPE_VALUE

IMAGE_FILE_DIALOG_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)"
"""Filtro de QFileDialog.getOpenFileName cuando el tipo de fuente
elegido es Imagen -- ayuda a no elegir por error un archivo que no es
una imagen, pero no es una validación real (la extensión no garantiza
el contenido); IndexImageSource ya reporta con claridad si el archivo
elegido no resulta ser una imagen válida al intentar embeberlo."""


def image_file_dialog_filter(source_type: str) -> str:
    """Filtro a pasar a QFileDialog.getOpenFileName -- restringido a
    extensiones de imagen cuando `source_type` es Imagen, sin filtro
    (cadena vacía = "todos los archivos") para cualquier otro tipo,
    mismo comportamiento que antes de esta ronda."""
    if source_type == IMAGE_SOURCE_TYPE_VALUE:
        return IMAGE_FILE_DIALOG_FILTER
    return ""


def image_preview_placeholder_text(source_type: str, location: str) -> Optional[str]:
    """Texto a mostrar en la vista previa ANTES de intentar cargar el
    archivo como imagen, o None cuando sí corresponde intentarlo
    (`source_type` es Imagen y `location` no está vacía) -- en ese caso
    quien llama (el widget Qt) intenta un QPixmap real y decide su
    propio texto de repuesto si la carga falla (ver
    _RegisterSourceDialog._update_image_preview): esta función no sabe
    nada de QPixmap a propósito, para poder probarse sin Qt."""
    if source_type != IMAGE_SOURCE_TYPE_VALUE:
        return "(vista previa no aplica a este tipo de fuente)"
    if not location.strip():
        return "(elige un archivo para ver la vista previa)"
    return None
