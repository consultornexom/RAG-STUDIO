"""Comando: indexar la imagen de una fuente IMAGEN_NATIVA (embeber +
subir a la colección de imágenes del VectorStore). Fase 3 del diseño de
multimodalidad nativa (RAG 3, ver docs proyecto/RAG_STUDIO_Diseno_
Ejecutable_RAG3_Multimodalidad.docx, sección 3.4) -- hermano de
IndexSource, pero para SourceType.IMAGEN_NATIVA en vez de fuentes de
texto.

Diferencia deliberada con IndexSource (ver Ronda 65, punto 221): este
comando NO parte de Chunk ya producidos por FragmentSource -- una
imagen nativa no tiene texto que fragmentar, así que FragmentSource no
puede ser quien produzca el Chunk final (no recibe SourceRepository en
su constructor, no puede llegar a `Source.original_copy_path`). En vez
de eso, IndexImageSource lee el Source directamente y construye él
mismo el único Chunk tipo IMAGEN de esa fuente.
"""
from __future__ import annotations

from pathlib import Path

from domain.documents.entities import SourceType
from domain.documents.exceptions import SourceNotFoundError
from domain.documents.ports import SourceRepository
from domain.ingestion.entities import Chunk, ChunkType
from domain.ingestion.ports import ChunkRepository
from domain.rag.entities import IMAGE_COLLECTION_NAME, VectorPoint
from domain.rag.exceptions import NotAnImageSourceError
from domain.rag.ports import ImageEmbeddingProvider, VectorStore


class IndexImageSource:
    def __init__(
        self,
        source_repository: SourceRepository,
        chunk_repository: ChunkRepository,
        image_embedding_provider: ImageEmbeddingProvider,
        vector_store: VectorStore,
    ):
        self._sources = source_repository
        self._chunks = chunk_repository
        self._embedder = image_embedding_provider
        self._store = vector_store

    def execute(self, project_id: str, source_id: str) -> int:
        """Indexa (o reindexa) la imagen de una fuente IMAGEN_NATIVA.
        Devuelve 1 si quedó indexada, 0 si la fuente todavía no tiene
        una copia de archivo legible (`Source.original_copy_path`
        vacío -- p. ej. la copia falló al registrar la fuente, o
        `location` estaba vacía): 0 es un resultado válido, no un
        error, mismo criterio que IndexSource con una fuente sin
        fragmentar todavía.

        Lanza SourceNotFoundError si la fuente no existe, y
        NotAnImageSourceError si existe pero no es SourceType.
        IMAGEN_NATIVA -- a diferencia de IndexSource (sirve para
        cualquier tipo de fuente indistintamente), este comando es
        específico de imágenes nativas.

        Siempre borra primero el Chunk y el/los punto(s) anteriores de
        esta fuente (tanto en ChunkRepository como en la colección de
        imágenes del VectorStore) antes de volver a indexar -- mismo
        criterio idempotente que IndexSource: no se promete que el id
        del Chunk de imagen sea estable entre corridas.

        Auditoria profunda (ronda posterior a la 76, ver bitacora): el
        borrado ya NO ocurre antes de calcular el embedding de la
        imagen ni antes de `ensure_collection` -- mismo hallazgo y
        misma correccion que en IndexSource.execute (ver ese docstring
        para el detalle): si `embed_images` (sin red para el primer uso
        del modelo) o `ensure_collection` (cambio de perfil de
        embeddings de imagen) fallaban, la fuente quedaba con CERO
        chunks/vectores, peor que antes de pedir el reindexado. Ahora
        ambos pasos ocurren ANTES de tocar el indice/chunk viejo.
        """
        source = self._sources.get(project_id, source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.source_type != SourceType.IMAGEN_NATIVA:
            raise NotAnImageSourceError(source_id, source.source_type.value)

        if not source.original_copy_path:
            # Sin copia de archivo legible: sigue siendo correcto
            # borrar cualquier chunk/vector viejo (p. ej. la copia
            # existía antes y se perdió) -- no hay ningún paso
            # posterior aquí que pueda fallar y dejar un estado peor.
            self._chunks.delete_for_source(project_id, source_id)
            self._store.delete_for_source(project_id, source_id, collection=IMAGE_COLLECTION_NAME)
            return 0

        [vector] = self._embedder.embed_images([source.original_copy_path])
        self._store.ensure_collection(
            project_id, self._embedder.dimensions, collection=IMAGE_COLLECTION_NAME,
        )

        chunk = Chunk(
            project_id=project_id,
            source_id=source_id,
            chunk_index=0,
            text="",
            token_count=0,
            chunk_type=ChunkType.IMAGEN,
            # Ver Chunk.image_relative_path: ruta relativa dentro de
            # sources/original/ del proyecto -- store_original() siempre
            # guarda el archivo directamente en ese directorio (sin
            # subcarpetas), así que basta con el nombre de archivo.
            image_relative_path=Path(source.original_copy_path).name,
        )
        point = VectorPoint(
            id=chunk.id,
            vector=vector,
            payload={"source_id": source_id, "chunk_index": 0},
        )

        self._chunks.delete_for_source(project_id, source_id)
        self._store.delete_for_source(project_id, source_id, collection=IMAGE_COLLECTION_NAME)
        self._chunks.save_many(project_id, [chunk])
        self._store.upsert(project_id, [point], collection=IMAGE_COLLECTION_NAME)
        return 1
