"""Consulta: busqueda semantica sobre los fragmentos indexados de un
proyecto."""
from __future__ import annotations

from collections.abc import Collection
from typing import Optional

from pydantic import BaseModel

from domain.documents.entities import AccessLevel
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk
from domain.ingestion.ports import ChunkRepository
from domain.rag.exceptions import SourceFilterUnavailableError
from domain.rag.ports import EmbeddingProvider, VectorStore

from .._source_usability import is_usable_source, passes_access_level


class SemanticSearchResult(BaseModel):
    """Un resultado ya unido con el Chunk completo -- el VectorStore
    solo conoce id + payload; el texto real siempre se lee de
    ChunkRepository (fuente de verdad del contenido, igual que en la
    Etapa 3).

    `parent_chunk` (Pista B.1 del ADR-003, docs proyecto/
    RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 6): solo
    se puebla cuando se pidió `expand_to_parent=True` en la búsqueda Y
    `chunk.parent_chunk_id` no es None. Se decidió "adjuntar" en vez de
    "reemplazar" el chunk encontrado -- `chunk` sigue siendo el
    fragmento exacto que de verdad coincidió con la consulta (y su
    `score` se calculó sobre ese texto puntual, no sobre la sección
    completa); `parent_chunk` es contexto adicional opcional para quien
    consuma el resultado (UI o agente externo) decida si mostrar el
    extracto puntual, la sección completa, o ambos. Reemplazar el
    texto habría ocultado cuál fue el fragmento que realmente hizo
    match, perdiendo trazabilidad -- documento maestro, criterio de
    citabilidad exacta (página, sección)."""

    chunk: Chunk
    score: float
    parent_chunk: Optional[Chunk] = None


class SemanticSearch:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        chunk_repository: ChunkRepository,
        source_repository: Optional[SourceRepository] = None,
    ):
        # source_repository es opcional (capacidad opcional, mismo
        # patron que embedding_provider_factory en RagService): sin el,
        # only_usable_sources=True no esta disponible -- ver
        # SourceFilterUnavailableError.
        self._embedder = embedding_provider
        self._store = vector_store
        self._chunks = chunk_repository
        self._sources = source_repository

    def execute(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        expand_to_parent: bool = False, max_access_level: Optional[AccessLevel] = None,
        source_ids: Optional[Collection[str]] = None,
    ) -> list[SemanticSearchResult]:
        """source_ids (Ronda 89): restringe la búsqueda a ese conjunto de
        fuentes ANTES de elegir los mejores resultados. Lo usa el motor
        conversacional para aplicar los filtros de metadatos: antes se
        filtraba después de tomar el top-k global y, si las mejores
        coincidencias eran de otras fuentes, el filtro dejaba muy pocos
        resultados (o ninguno) de la fuente correcta. Conjunto vacío =
        ningún resultado."""
        if not query_text.strip():
            raise ValueError("La consulta de búsqueda no puede estar vacía")
        if (only_usable_sources or max_access_level is not None) and self._sources is None:
            raise SourceFilterUnavailableError()
        # embed_query (no embed_texts): la consulta es el lado
        # "pregunta", que para un modelo asimétrico necesita un
        # tratamiento distinto al de los pasajes que indexa IndexSource
        # (ver domain.rag.ports.EmbeddingProvider.embed_query).
        query_vector = self._embedder.embed_query(query_text)
        if source_ids is not None:
            hits = self._search_in_sources(project_id, query_vector, limit, source_id, source_ids)
        else:
            hits = self._store.search(project_id, query_vector, limit=limit, source_id=source_id)

        results: list[SemanticSearchResult] = []
        for hit in hits:
            chunk = self._chunks.get(project_id, hit.chunk_id)
            if chunk is None:
                # El punto quedo huerfano (p. ej. se reindexo la fuente
                # sin borrar antes, o se edito el proyecto por fuera de
                # la app) -- se omite en vez de fallar toda la búsqueda.
                continue
            if only_usable_sources and not is_usable_source(self._sources, project_id, chunk.source_id):
                # Documento maestro, "supuestos prohibidos": no usar
                # documentos rechazados, vencidos o no validados. Se
                # filtra aqui (al momento de "usar" el resultado), no al
                # indexar -- una fuente puede volverse RECHAZADO/VENCIDO
                # despues de haberse indexado, sin que nadie vuelva a
                # ejecutar "Indexar esta fuente"; filtrar solo al
                # indexar dejaria vectores obsoletos disponibles para
                # siempre. El resultado puede tener menos de `limit`
                # elementos si se excluyen candidatos -- se prefiere
                # devolver de menos que arriesgarse a filtrar de mas.
                continue
            if not passes_access_level(self._sources, project_id, chunk.source_id, max_access_level):
                # Pista B.3 del ADR-003: mismo criterio que el filtro de
                # arriba -- se evalua al usar el resultado, no al
                # indexar, porque access_level puede cambiar despues de
                # indexar una fuente sin que nadie vuelva a indexarla.
                continue
            parent_chunk = None
            if expand_to_parent and chunk.parent_chunk_id is not None:
                # Igual que el punto orfano de arriba: si el padre ya
                # no existe (p. ej. se re-fragmento la fuente entre la
                # indexacion y esta busqueda), se deja parent_chunk en
                # None en vez de fallar toda la busqueda -- el chunk
                # hijo encontrado sigue siendo un resultado valido por
                # si mismo.
                parent_chunk = self._chunks.get(project_id, chunk.parent_chunk_id)
            results.append(SemanticSearchResult(chunk=chunk, score=hit.score, parent_chunk=parent_chunk))
        return results

    _MAX_PER_SOURCE_QUERIES = 25

    def _search_in_sources(
        self, project_id: str, query_vector: list[float], limit: int,
        source_id: Optional[str], source_ids: Collection[str],
    ) -> list:
        allowed = set(source_ids)
        if source_id is not None:
            allowed &= {source_id}
        if not allowed:
            return []
        if len(allowed) <= self._MAX_PER_SOURCE_QUERIES:
            # Una consulta por fuente con el filtro nativo del índice: el
            # top-k de cada una es exacto, sin depender de cuántos
            # fragmentos de OTRAS fuentes se parezcan más a la consulta.
            hits = []
            for allowed_id in sorted(allowed):
                hits.extend(self._store.search(project_id, query_vector, limit=limit, source_id=allowed_id))
            hits.sort(key=lambda hit: hit.score, reverse=True)
            return hits[:limit]
        # Muchas fuentes permitidas: se pide un conjunto amplio y se filtra.
        pool = self._store.search(project_id, query_vector, limit=max(limit * 20, 400))
        return [hit for hit in pool if hit.payload.get("source_id") in allowed][:limit]
