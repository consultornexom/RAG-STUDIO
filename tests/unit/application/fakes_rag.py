"""Dobles de prueba en memoria para el contexto RAG (Etapa 4)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from domain.rag.entities import DEFAULT_COLLECTION_NAME, IndexInfo, VectorPoint, VectorSearchHit, cosine_similarity
from domain.rag.exceptions import EmbeddingDimensionMismatchError
from domain.rag.ports import EmbeddingProvider, ImageEmbeddingProvider, IndexInfoRepository, Reranker, VectorStore


class FakeEmbeddingProvider(EmbeddingProvider):
    """Vectores deterministicos derivados de un hash del texto -- no
    tienen ningun significado semantico real, solo permiten probar el
    pipeline (indexar, buscar, filtrar) sin depender de red ni de un
    modelo real de fastembed."""

    def __init__(self, dimensions: int = 4, provider_name: str = "fake", model_name: str = "fake-hash"):
        self._dimensions = dimensions
        self._provider_name = provider_name
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([digest[i] / 255.0 for i in range(self._dimensions)])
        return vectors


class WordOverlapFakeEmbeddingProvider(EmbeddingProvider):
    """Fake embebedor cuya similitud de coseno SÍ refleja vocabulario
    compartido -- a diferencia de FakeEmbeddingProvider (arriba), cuyos
    vectores son ruido determinista derivado de un hash del texto
    completo, sin ninguna relación con el significado ni con palabras
    compartidas entre dos textos. Ese ruido es suficiente para las
    pruebas de indexación/búsqueda (que solo verifican que el mecanismo
    funciona), pero produce coincidencias falsas al probarlo con el
    emparejamiento SEMÁNTICO de intención (domain.conversational.
    intent_matching): dos textos sin ninguna palabra en común pueden
    terminar con un coseno positivo por pura coincidencia del hash.

    Aquí cada palabra distinta recibe su propia posición fija del
    vector, asignada por orden de aparición (un diccionario interno
    persistente, no un hash con posibilidad de colisión): dos textos con
    vocabulario real en común terminan con coseno alto, y dos sin nada
    en común terminan exactamente en 0 -- suficiente para probar la
    lógica de combinación léxico+semántico sin necesitar un modelo real
    de fastembed. `_CAPACITY` es solo un tope generoso de vocabulario
    distinto que puede ver una sola instancia (de sobra para cualquier
    prueba); todos los vectores devueltos tienen ese mismo largo fijo,
    para que dos llamadas separadas (`embed_query` y `embed_texts`)
    sigan siendo comparables entre sí sin importar el orden en que se
    vieron las palabras."""

    _CAPACITY = 4096

    def __init__(self):
        self._word_index: dict[str, int] = {}

    @property
    def provider_name(self) -> str:
        return "fake-word-overlap"

    @property
    def model_name(self) -> str:
        return "fake-word-overlap"

    @property
    def dimensions(self) -> int:
        return self._CAPACITY

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector_for(text)

    def _vector_for(self, text: str) -> list[float]:
        vector = [0.0] * self._CAPACITY
        for word in text.lower().split():
            index = self._word_index.setdefault(word, len(self._word_index))
            if index < self._CAPACITY:
                vector[index] += 1.0
        return vector


class FakeVectorStore(VectorStore):
    """Indice vectorial en memoria con similitud coseno real (no es un
    doble "tonto": calcula distancia de verdad para que las pruebas de
    orden de resultados sean significativas).

    `collection` (Fase 3 de multimodalidad nativa, RAG 3): cada
    proyecto puede tener varias colecciones independientes (mismo
    criterio que QdrantLocalVectorStore desde la Fase 1) -- `_points`/
    `_collections` quedan anidados por project_id y luego por
    collection, en vez de una sola clave plana, para que dos
    colecciones del mismo proyecto (p. ej. "chunks" y
    "chunks_imagenes") nunca compartan ni pisen los puntos entre sí."""

    def __init__(self):
        self._collections: dict[str, dict[str, int]] = {}  # project_id -> {collection: vector_size}
        self._points: dict[str, dict[str, dict[str, VectorPoint]]] = {}  # project_id -> {collection: {id: point}}

    def ensure_collection(
        self, project_id: str, vector_size: int, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        by_collection = self._collections.setdefault(project_id, {})
        existing = by_collection.get(collection)
        if existing is not None and existing != vector_size:
            raise EmbeddingDimensionMismatchError(
                f"El proyecto {project_id!r} (coleccion {collection!r}) ya tiene un "
                f"indice de dimension {existing}, no {vector_size}."
            )
        by_collection[collection] = vector_size

    def upsert(
        self, project_id: str, points: list[VectorPoint], *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        bucket = self._points.setdefault(project_id, {}).setdefault(collection, {})
        for point in points:
            bucket[point.id] = point

    def delete_for_source(
        self, project_id: str, source_id: str, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        bucket = self._points.setdefault(project_id, {}).get(collection, {})
        for point_id in [pid for pid, p in bucket.items() if p.payload.get("source_id") == source_id]:
            del bucket[point_id]

    def search(
        self, project_id: str, query_vector: list[float], limit: int,
        source_id: Optional[str] = None, *, collection: str = DEFAULT_COLLECTION_NAME,
    ) -> list[VectorSearchHit]:
        bucket = self._points.get(project_id, {}).get(collection, {})
        candidates = bucket.values()
        if source_id is not None:
            candidates = [p for p in candidates if p.payload.get("source_id") == source_id]
        scored = [(p, cosine_similarity(query_vector, p.vector)) for p in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            VectorSearchHit(chunk_id=p.id, score=score, payload=dict(p.payload))
            for p, score in scored[:limit]
        ]

    def count(self, project_id: str, *, collection: str = DEFAULT_COLLECTION_NAME) -> int:
        return len(self._points.get(project_id, {}).get(collection, {}))


class FakeReranker(Reranker):
    """Reranker de prueba (ADR-003, Pista A.2): determinista, sin
    ningún modelo real -- da mayor puntaje a los textos que contienen
    la palabra "relevante", el resto queda en 0.0. Suficiente para
    probar que HybridSearch/RagService de verdad usan estos puntajes
    (y no el score de fusión RRF) cuando rerank=True, sin depender de
    fastembed ni de red."""

    def __init__(self, model_name: str = "fake-reranker"):
        self._model_name = model_name
        self.received_query: Optional[str] = None
        self.received_passages: list[str] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(self, query_text: str, passages: list[str]) -> list[float]:
        self.received_query = query_text
        self.received_passages = list(passages)
        return [1.0 if "relevante" in passage else 0.0 for passage in passages]


class FakeImageEmbeddingProvider(ImageEmbeddingProvider):
    """Vectores deterministicos derivados de un hash, mismo criterio que
    FakeEmbeddingProvider -- pero aquí `embed_images` hashea el nombre
    de archivo SIN extensión (Path.stem) de cada ruta, y
    `embed_query_text` hashea el texto de consulta tal cual. Una prueba
    que consulte con el mismo texto que el nombre de archivo de una
    imagen ya indexada obtiene por diseño el vector idéntico (coseno
    1.0) -- suficiente para probar el mecanismo real de
    IndexImageSource/SemanticSearchImages sin necesitar ningún modelo
    CLIP real."""

    def __init__(self, dimensions: int = 4, provider_name: str = "fake-image", model_name: str = "fake-image-hash"):
        self._dimensions = dimensions
        self._provider_name = provider_name
        self._model_name = model_name
        # Contador de llamadas (Ronda 68): permite probar que
        # SemanticSearchImages evita embeber la consulta cuando el
        # proyecto no tiene ninguna imagen indexada -- ver el atajo de
        # VectorStore.count() en ese módulo, agregado justamente para no
        # pagar el costo de cargar/descargar el modelo real de texto
        # pareado (FastEmbedImageProvider) en cada mensaje de un
        # proyecto puramente textual.
        self.embed_query_text_calls: list[str] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vector_for(self, label: str) -> list[float]:
        digest = hashlib.sha256(label.encode("utf-8")).digest()
        return [digest[i] / 255.0 for i in range(self._dimensions)]

    def embed_images(self, image_paths: list[str]) -> list[list[float]]:
        return [self._vector_for(Path(p).stem) for p in image_paths]

    def embed_query_text(self, text: str) -> list[float]:
        self.embed_query_text_calls.append(text)
        return self._vector_for(text)


class InMemoryIndexInfoRepository(IndexInfoRepository):
    def __init__(self):
        self._by_project: dict[str, IndexInfo] = {}

    def save(self, info: IndexInfo) -> None:
        self._by_project[info.project_id] = info

    def get(self, project_id: str) -> Optional[IndexInfo]:
        return self._by_project.get(project_id)
