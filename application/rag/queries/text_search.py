"""Consulta: búsqueda textual (palabra clave, BM25) sobre los
fragmentos de un proyecto -- complemento de SemanticSearch (Etapa 4,
Laboratorio RAG: "búsqueda semántica/textual/híbrida" del documento
maestro).

A diferencia de SemanticSearch, no necesita un índice vectorial ni
haber corrido "Indexar esta fuente": BM25 se calcula bajo demanda sobre
los fragmentos ya guardados por ChunkRepository, igual que el
comparador de modelos de embeddings (ver
application.rag.queries.compare_embedding_profiles) -- mismo criterio
de "barrido en memoria suficiente para un proyecto típico", ver
docstring de domain.rag.text_search.bm25_scores para la ruta de
escalamiento si algún día no lo es."""
from __future__ import annotations

from collections.abc import Collection
from typing import Optional

from domain.documents.entities import AccessLevel
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk, ChunkType
from domain.ingestion.ports import ChunkRepository
from domain.rag.exceptions import SourceFilterUnavailableError
from domain.rag.text_search import bm25_scores

from .._source_usability import is_usable_source, passes_access_level
from .semantic_search import SemanticSearchResult


class TextSearch:
    def __init__(
        self,
        chunk_repository: ChunkRepository,
        source_repository: Optional[SourceRepository] = None,
    ):
        self._chunks = chunk_repository
        self._sources = source_repository

    def execute(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        expand_to_parent: bool = False, max_access_level: Optional[AccessLevel] = None,
        source_ids: Optional[Collection[str]] = None,
    ) -> list[SemanticSearchResult]:
        if not query_text.strip():
            raise ValueError("La consulta de búsqueda no puede estar vacía")
        if (only_usable_sources or max_access_level is not None) and self._sources is None:
            raise SourceFilterUnavailableError()

        chunks: list[Chunk] = (
            self._chunks.list_for_source(project_id, source_id) if source_id
            else self._chunks.list_for_project(project_id)
        )
        # Pista B.1 del ADR-003 (mismo criterio que IndexSource al
        # indexar a embeddings/VectorStore, ver
        # application/rag/commands/index_source.py): un chunk PADRE
        # nunca debe competir en un resultado de búsqueda contra sus
        # propios hijos -- a diferencia del VectorStore, BM25 no tiene
        # ningún filtro previo de "qué se indexó", así que sin este
        # filtro aquí, un padre con texto de sección completa (que por
        # construcción repite el vocabulario de todos sus hijos)
        # aparecería como resultado propio, además de -- no en vez de
        # -- los hijos que expand_to_parent ya expone como contexto.
        chunks = [c for c in chunks if c.chunk_type != ChunkType.PADRE]
        if source_ids is not None:
            # Ronda 89: mismo criterio que SemanticSearch -- se restringe
            # antes de puntuar, no después de elegir el top-k.
            allowed = set(source_ids)
            chunks = [c for c in chunks if c.source_id in allowed]
        if only_usable_sources:
            chunks = [c for c in chunks if is_usable_source(self._sources, project_id, c.source_id)]
        if max_access_level is not None:
            chunks = [
                c for c in chunks if passes_access_level(self._sources, project_id, c.source_id, max_access_level)
            ]
        if not chunks:
            return []

        scores = bm25_scores(query_text, [chunk.text for chunk in chunks])
        # BM25 da 0.0 a un fragmento sin ningún término de la consulta
        # -- se descarta en vez de devolverlo como "resultado" sin
        # ninguna coincidencia real (a diferencia de la búsqueda
        # semántica, donde el VectorStore siempre trae los top-K más
        # cercanos aunque el score sea bajo: aquí "bajo" y "cero" son
        # cosas distintas, cero significa "ninguna palabra en común").
        scored = [
            SemanticSearchResult(chunk=chunk, score=score)
            for chunk, score in zip(chunks, scores, strict=True) if score > 0.0
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        top = scored[:limit]
        if not expand_to_parent:
            return top
        # Se expande solo sobre los `limit` finales (no sobre todos los
        # candidatos con score > 0.0) -- Pista B.1 del ADR-003: no tiene
        # sentido pagar una consulta a ChunkRepository.get por cada
        # candidato descartado antes de recortar a `limit`.
        return [
            result if result.chunk.parent_chunk_id is None else result.model_copy(
                update={"parent_chunk": self._chunks.get(project_id, result.chunk.parent_chunk_id)}
            )
            for result in top
        ]
