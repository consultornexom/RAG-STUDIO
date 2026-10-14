"""Ayuda compartida entre SemanticSearch, TextSearch y HybridSearch:
filtrar resultados por fuentes usables para respuestas (Módulo 4,
"control de documentos excluidos" -- documento maestro, "supuestos
prohibidos": no usar documentos rechazados, vencidos o no validados).

Vive fuera de cualquiera de las tres clases porque las tres necesitan
exactamente la misma regla -- duplicarla sería el mismo riesgo que
tener dos definiciones de "similitud coseno" en el proyecto (ver
bitácora sobre el refactor de FakeVectorStore para reusar
domain.rag.entities.cosine_similarity)."""
from __future__ import annotations

from typing import Optional

from domain.documents.entities import AccessLevel, is_within_access_level
from domain.documents.ports import SourceRepository


def is_usable_source(
    source_repository: Optional[SourceRepository], project_id: str, source_id: str,
) -> bool:
    """True si la fuente existe y está VALIDADO + vigente. Una fuente
    que ya no existe en el repositorio (huérfana) se trata como no
    usable, no como "usable por defecto" -- lo más seguro ante datos
    inconsistentes."""
    if source_repository is None:
        return True
    source = source_repository.get(project_id, source_id)
    return source is not None and source.is_usable_for_responses()


def passes_access_level(
    source_repository: Optional[SourceRepository], project_id: str, source_id: str,
    max_access_level: Optional[AccessLevel],
) -> bool:
    """True si la fuente de este chunk no excede `max_access_level`
    (Pista B.3 del ADR-003, control de acceso en tiempo de consulta).
    `max_access_level=None` significa "sin techo" (comportamiento
    actual, sin este filtro) -- True siempre. Una fuente huérfana (ya
    no existe en el repositorio) se trata como que SÍ excede el techo,
    no como "pasa por defecto" -- mismo criterio conservador que
    `is_usable_source` ante datos inconsistentes."""
    if max_access_level is None or source_repository is None:
        return True
    source = source_repository.get(project_id, source_id)
    if source is None:
        return False
    return is_within_access_level(source.access_level, max_access_level)
