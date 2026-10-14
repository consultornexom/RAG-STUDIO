"""Consulta: filtros y agregaciones deterministas sobre los bloques
estructurados ya fragmentados (Pista B.2b del ADR-003, docs proyecto/
RAG_STUDIO_Diseno_B2_Datos_Estructurados.docx, sección 3.3).

Mismo criterio ya usado por TextSearch/get_coverage_report: en memoria,
sobre lo que ya devuelve ChunkRepository -- sin índice ni infraestructura
nueva. domain.rag.structured_query es quien sabe filtrar/agregar filas
puras; este módulo solo sabe reunir esas filas a partir de los chunks
ChunkType.ESTRUCTURADO del proyecto (o de una fuente, si se pide).

Auditoria profunda (ronda posterior a la 76, ver bitacora): esta
consulta se sumo en la Ronda 28 (Pista B.4), un round DESPUES de que la
Ronda 27 (Pista B.3, control de acceso) enhebrara only_usable_sources/
max_access_level en SemanticSearch/TextSearch/HybridSearch -- y nunca
recibio ese mismo hilo. Efecto real: `SimulateConversation._query_structured`
(el camino ESTRUCTURADO de una conversacion real, incluida la que
atiende un WidgetToken publico con `max_access_level="publico"`) podia
devolver filas de una fuente RESTRINGIDA, no vigente o no validada,
sin ningun filtro -- exactamente lo que Modulo 4 y la Pista B.3
prohiben para las otras tres vias de busqueda. Correccion: mismos dos
parametros opcionales, mismo criterio ("capacidad opcional, quien no
la pida no ve ningun cambio"), aplicados por fila (cada
StructuredQueryRow ya lleva source_id)."""
from __future__ import annotations

from typing import Optional

from domain.documents.entities import AccessLevel
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk, ChunkType
from domain.ingestion.ports import ChunkRepository
from domain.rag.exceptions import SourceFilterUnavailableError
from domain.rag.structured_query import (
    StructuredAggregation, StructuredFilter, StructuredQueryResult, StructuredQueryRow,
    apply_aggregation, apply_filters,
)

from .._source_usability import is_usable_source, passes_access_level


class StructuredQuery:
    def __init__(self, chunk_repository: ChunkRepository, source_repository: Optional[SourceRepository] = None):
        # source_repository es opcional, mismo patron que en
        # SemanticSearch/TextSearch/HybridSearch: sin el,
        # only_usable_sources=True/max_access_level no distinto de None
        # lanzan SourceFilterUnavailableError en vez de fallar en
        # silencio -- ver execute().
        self._chunks = chunk_repository
        self._sources = source_repository

    def execute(
        self, project_id: str,
        filters: Optional[list[StructuredFilter]] = None,
        aggregation: Optional[StructuredAggregation] = None,
        source_id: Optional[str] = None,
        only_usable_sources: bool = False,
        max_access_level: Optional[AccessLevel] = None,
    ) -> StructuredQueryResult:
        """Sin bloques ESTRUCTURADO en el proyecto (o en la fuente
        pedida) -- fuentes no XLSX/CSV, o extraídas/fragmentadas antes
        de la Pista B.2 -- devuelve un resultado vacío (rows=[],
        aggregation=None o buckets sin filas), nunca un error: mismo
        criterio que "sin dato estructurado" documentado en la sección
        3.4 del diseño.

        only_usable_sources/max_access_level: mismo significado y
        misma excepción (SourceFilterUnavailableError sin
        source_repository configurado) que en SemanticSearch/
        TextSearch/HybridSearch -- se filtra por fila (cada
        StructuredQueryRow.source_id) antes de aplicar filters/
        aggregation, para que una agregación (conteo, suma, promedio)
        tampoco arrastre filas de una fuente excluida."""
        if (only_usable_sources or max_access_level is not None) and self._sources is None:
            raise SourceFilterUnavailableError()
        chunks: list[Chunk] = (
            self._chunks.list_for_source(project_id, source_id) if source_id
            else self._chunks.list_for_project(project_id)
        )
        rows: list[StructuredQueryRow] = []
        for chunk in chunks:
            if chunk.chunk_type != ChunkType.ESTRUCTURADO or not chunk.structured_content:
                continue
            if only_usable_sources and not is_usable_source(self._sources, project_id, chunk.source_id):
                continue
            if not passes_access_level(self._sources, project_id, chunk.source_id, max_access_level):
                continue
            for row_index, fila in enumerate(chunk.structured_content.get("filas", [])):
                rows.append(StructuredQueryRow(
                    chunk_id=chunk.id, source_id=chunk.source_id,
                    section_title=chunk.section_title, row_index=row_index, values=fila,
                ))

        filtered = apply_filters(rows, filters or [])
        result = StructuredQueryResult(rows=filtered)
        if aggregation is not None:
            result.aggregation = apply_aggregation(filtered, aggregation)
        return result
