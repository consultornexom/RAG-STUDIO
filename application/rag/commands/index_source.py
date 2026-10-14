"""Comando: indexar los fragmentos de una fuente (embeber + subir al
VectorStore). Núcleo de la Etapa 4, sobre los Chunk que ya produce
FragmentSource (Etapa 3)."""
from __future__ import annotations

import re

from domain.ingestion.entities import ChunkType
from domain.ingestion.ports import ChunkRepository
from domain.rag.entities import IndexInfo, VectorPoint
from domain.rag.ports import EmbeddingProvider, IndexInfoRepository, VectorStore


class IndexSource:
    def __init__(
        self,
        chunk_repository: ChunkRepository,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        index_info_repository: IndexInfoRepository,
    ):
        self._chunks = chunk_repository
        self._embedder = embedding_provider
        self._store = vector_store
        self._index_info = index_info_repository

    def execute(self, project_id: str, source_id: str) -> int:
        """Indexa (o reindexa) todos los fragmentos de una fuente.
        Devuelve cuantos fragmentos quedaron indexados -- 0 es un
        resultado valido (fuente sin fragmentar todavia), no un
        error.

        Siempre borra primero los vectores anteriores de esta fuente
        (VectorStore.delete_for_source), igual que FragmentSource
        borra los Chunk anteriores antes de guardar los nuevos: los
        ids de Chunk no se prometen estables entre corridas de
        fragmentacion, asi que "actualizar in place" no es una opcion
        segura -- hay que limpiar y volver a subir.

        Auditoria profunda (ronda posterior a la 76, ver bitacora): el
        borrado ya NO ocurre antes de calcular los embeddings nuevos ni
        antes de `ensure_collection` -- ocurria antes, y si cualquiera
        de esos dos pasos fallaba (EmbeddingProviderError sin red para
        el primer uso de un modelo; EmbeddingDimensionMismatchError si
        el perfil de embeddings del proyecto cambio desde la ultima
        indexacion), la fuente quedaba con CERO vectores -- peor que
        antes de pedir el reindexado, sin ningun rollback ni aviso mas
        alla de la excepcion misma. Ahora ambos pasos ocurren ANTES de
        tocar el indice viejo: si fallan, la excepcion se propaga igual
        que siempre, pero los vectores anteriores de esta fuente
        siguen intactos."""
        chunks = self._chunks.list_for_source(project_id, source_id)
        # Pista B.1 del ADR-003 (docs proyecto/
        # RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, secciones 3.2
        # y 7): un chunk PADRE es un Chunk real en SQLite -- se recupera
        # por id para expandir contexto -- pero JAMAS debe llegar al
        # embedding provider ni al VectorStore. Indexarlo lo pondría a
        # competir en la búsqueda contra sus propios hijos (texto
        # duplicado, section_title repetido), degradando precisión sin
        # ningún beneficio.
        chunks = [
            c for c in chunks
            if _has_meaningful_content(c) and c.chunk_type != ChunkType.PADRE
        ]
        if not chunks:
            # Sin fragmentos reales que indexar (fuente recien
            # fragmentada sin contenido usable, o sin fragmentar
            # todavia): sigue siendo correcto borrar cualquier vector
            # viejo que haya quedado de una corrida anterior -- aqui no
            # hay ningun paso posterior que pueda fallar y dejar un
            # estado peor, a diferencia del camino con contenido real.
            self._store.delete_for_source(project_id, source_id)
            return 0

        vectors = self._embedder.embed_texts([chunk.text for chunk in chunks])
        self._store.ensure_collection(project_id, self._embedder.dimensions)

        points = [
            VectorPoint(
                id=chunk.id,
                vector=vector,
                payload=_build_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._store.delete_for_source(project_id, source_id)
        self._store.upsert(project_id, points)

        self._index_info.save(IndexInfo(
            project_id=project_id,
            embedding_provider=self._embedder.provider_name,
            embedding_model=self._embedder.model_name,
            dimensions=self._embedder.dimensions,
            points_count=self._store.count(project_id),
        ))
        return len(points)


def _has_meaningful_content(chunk) -> bool:
    """Descarta fragmentos que son solo un encabezado sin cuerpo
    propio (p. ej. un título de sección que solo agrupa subsecciones,
    como "Plan de Estudios" antes de "1er. Cuatrimestre"). La
    estrategia POR_ENCABEZADO nunca fusiona secciones distintas por
    diseño (ver domain.ingestion.entities.FragmentationStrategy), así
    que estos fragmentos "vacíos" quedan como Chunk real -- útiles
    para navegar la estructura del documento en la pestaña Ingesta --
    pero no aportan nada a la búsqueda semántica: su único contenido
    ya está capturado en section_title. Indexarlos igual los hacía
    competir (y a veces ganar) contra fragmentos con contenido real
    -- encontrado al probar con un documento real (ver bitácora del
    README).

    Solo los fragmentos con section_title (es decir, producidos por
    POR_ENCABEZADO) pueden ser "solo el título": un fragmento sin
    section_title (POR_TAMANIO, DOCUMENTO_COMPLETO, o cualquier texto
    corto legítimo de una sola línea) siempre se considera con
    contenido, para no descartar fragmentos cortos pero reales."""
    if not chunk.section_title:
        return True
    texto_sin_marca_de_encabezado = re.sub(r"^#+\s*", "", chunk.text.strip())
    return texto_sin_marca_de_encabezado != chunk.section_title


def _build_payload(chunk) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": chunk.source_id,
        "chunk_index": chunk.chunk_index,
        "section_title": chunk.section_title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
    }
    # Metadatos heredados con un prefijo, para no chocar con las
    # claves fijas de arriba si algún día un field_id se llama igual
    # (p. ej. "source_id" como campo de metadatos del proyecto).
    for key, value in chunk.inherited_metadata.items():
        payload[f"meta__{key}"] = value
    return payload
