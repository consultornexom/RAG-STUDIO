"""Lógica pura (sin Qt) para decidir cómo indexar una fuente desde el
botón "Indexar esta fuente" de IngestionPanel -- Fase 4 de
multimodalidad nativa (RAG 3). Mismo patrón ya establecido en este
proyecto para separar decisiones puras de los widgets Qt que las usan
(ver ui/conversational/parsing.py, ui/ingestion/search_highlighting.py,
ui/release/gate_status_logic.py)."""
from __future__ import annotations

from application.documents.options import IMAGE_SOURCE_TYPE_VALUE

INDEX_METHOD_TEXT = "index_source"
INDEX_METHOD_IMAGE = "index_image_source"


def index_method_for_source_type(source_type: str) -> str:
    """Nombre del método de RagService a invocar para indexar una
    fuente, según su tipo -- `index_image_source` (Fase 3, ver
    application/rag/commands/index_image_source.py) para
    SourceType.IMAGEN_NATIVA, `index_source` (el de siempre) para
    cualquier otro tipo. IngestionPanel._on_index resuelve el método
    real vía `getattr(rag_service, index_method_for_source_type(...))`
    en vez de duplicar aquí la llamada -- esta función solo decide EL
    NOMBRE, no conoce RagService."""
    if source_type == IMAGE_SOURCE_TYPE_VALUE:
        return INDEX_METHOD_IMAGE
    return INDEX_METHOD_TEXT
