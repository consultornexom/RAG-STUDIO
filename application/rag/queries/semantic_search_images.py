"""Consulta: búsqueda por similitud visual ("texto busca imagen") sobre
las imágenes nativas indexadas de un proyecto. Fase 3 del diseño de
multimodalidad nativa (RAG 3) -- hermana de SemanticSearch, pero sobre
la colección de imágenes (IMAGE_COLLECTION_NAME) en vez de la de texto.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from domain.documents.entities import AccessLevel
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk
from domain.ingestion.ports import ChunkRepository
from domain.rag.entities import IMAGE_COLLECTION_NAME
from domain.rag.exceptions import SourceFilterUnavailableError
from domain.rag.ports import ImageEmbeddingProvider, VectorStore

from .._source_usability import is_usable_source, passes_access_level


class ImageSearchResult(BaseModel):
    """Un resultado de búsqueda de imágenes, ya unido con el Chunk
    completo -- mismo criterio que SemanticSearchResult: el VectorStore
    solo conoce id + payload, el Chunk real (aquí, con
    `image_relative_path` poblado) siempre se lee de ChunkRepository.
    Sin `parent_chunk` -- a diferencia de los chunks de texto, un chunk
    de imagen no tiene jerarquía PADRE/hijo (Pista B.1 del ADR-003 no
    aplica a ChunkType.IMAGEN, ver Ronda 65)."""

    chunk: Chunk
    score: float


class SemanticSearchImages:
    def __init__(
        self,
        image_embedding_provider: ImageEmbeddingProvider,
        vector_store: VectorStore,
        chunk_repository: ChunkRepository,
        source_repository: Optional[SourceRepository] = None,
    ):
        # source_repository es opcional, mismo patrón de "capacidad
        # opcional" que SemanticSearch: sin él, only_usable_sources=True
        # no está disponible (ver SourceFilterUnavailableError).
        self._embedder = image_embedding_provider
        self._store = vector_store
        self._chunks = chunk_repository
        self._sources = source_repository

    def execute(
        self, project_id: str, query_text: str, limit: int = 5,
        source_id: Optional[str] = None, only_usable_sources: bool = False,
        max_access_level: Optional[AccessLevel] = None,
    ) -> list[ImageSearchResult]:
        if not query_text.strip():
            raise ValueError("La consulta de búsqueda no puede estar vacía")
        if (only_usable_sources or max_access_level is not None) and self._sources is None:
            raise SourceFilterUnavailableError()
        # Atajo antes de embeber la consulta: la mayoría de los
        # proyectos no tiene ninguna fuente IMAGEN_NATIVA indexada
        # todavía (image_embedding_provider hoy se conecta siempre,
        # tanto en el runtime de escritorio como en el runtime HTTP --
        # ver interfaces/api/runtime_context.py -- sin condicionarlo a
        # que el proyecto de verdad use imágenes). Sin este atajo, CADA
        # mensaje que responde pagaría el costo de cargar/descargar el
        # modelo de texto pareado de CLIP (ver FastEmbedImageProvider),
        # incluso en un proyecto puramente textual -- mismo criterio de
        # "no pagar por una capacidad que no se usa" que ya aplica
        # arriba a `only_usable_sources`/`max_access_level`.
        # VectorStore.count() es una operación barata (no embebe nada)
        # que ya devuelve 0 sin error si la colección todavía no existe.
        if self._store.count(project_id, collection=IMAGE_COLLECTION_NAME) == 0:
            return []
        # embed_query_text (no embed_images): el lado "texto" del
        # espacio compartido -- ver domain.rag.ports.
        # ImageEmbeddingProvider.embed_query_text. Puede lanzar
        # NotImplementedError si el proveedor configurado no tiene un
        # codificador de texto pareado (se deja propagar tal cual: es
        # un error de configuración del servicio, no de esta consulta).
        query_vector = self._embedder.embed_query_text(query_text)
        hits = self._store.search(
            project_id, query_vector, limit=limit, source_id=source_id,
            collection=IMAGE_COLLECTION_NAME,
        )

        results: list[ImageSearchResult] = []
        for hit in hits:
            chunk = self._chunks.get(project_id, hit.chunk_id)
            if chunk is None:
                # Punto huérfano (misma situación que SemanticSearch):
                # se omite en vez de fallar toda la búsqueda.
                continue
            if only_usable_sources and not is_usable_source(self._sources, project_id, chunk.source_id):
                continue
            if not passes_access_level(self._sources, project_id, chunk.source_id, max_access_level):
                continue
            results.append(ImageSearchResult(chunk=chunk, score=hit.score))
        return results
