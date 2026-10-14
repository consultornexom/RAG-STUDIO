"""Entidades del contexto RAG (Etapa 4 -- nucleo).

- IndexInfo: estado del indice vectorial de un proyecto (que modelo de
  embeddings se uso, cuantos puntos tiene). Un indice por proyecto en
  esta iteracion (no la matriz completa de EmbeddingModelConfig/Index
  versionados de ADR-001, seccion 5 -- eso queda para cuando se
  necesite comparar varias configuraciones de embeddings).
- VectorPoint: un vector + payload a insertar en el VectorStore.
- VectorSearchHit: un resultado crudo de busqueda vectorial (antes de
  unirse con el Chunk completo en application).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_MIN_RELEVANT_SCORE = 0.35
"""Umbral de similitud coseno por debajo del cual un resultado de
busqueda semantica se considera de baja relevancia. Surge de un
hallazgo real de validacion visual: buscar "Tiempo" sobre un plan de
estudios sin relacion tematica devolvio resultados con score
0.14-0.28, y no habia forma de que el usuario supiera si eso era
correcto o un error. No es un filtro que oculte resultados -- el
VectorStore siempre regresa los top-K mas cercanos aunque el score sea
bajo -- es solo la senal que usa la capa de aplicacion/UI para advertir
al usuario."""


DEFAULT_COLLECTION_NAME = "chunks"
"""Nombre de la coleccion de texto en el VectorStore de un proyecto --
unico valor por defecto de `collection` en los 5 metodos del puerto
VectorStore (ver domain.rag.ports.VectorStore) desde la Fase 3 del
diseno de multimodalidad nativa (RAG 3, ver docs proyecto/
RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx). Antes de esta
ronda este nombre vivia como una constante privada
(_COLLECTION_NAME) dentro del adaptador concreto
infrastructure.vectorstores.qdrant_local_store -- se promueve aqui, al
dominio, para que el propio puerto (no solo un adaptador) pueda ofrecer
un valor por defecto sin que application tenga que conocer un nombre de
coleccion "magico" definido en infrastructure (ADR-001, seccion 4)."""

IMAGE_COLLECTION_NAME = "chunks_imagenes"
"""Nombre de la coleccion separada donde se indexan los vectores de
imagen (ImageEmbeddingProvider.embed_images), dentro del mismo
VectorStore/directorio de indice que DEFAULT_COLLECTION_NAME -- ver
docstring de infrastructure.vectorstores.qdrant_local_store sobre por
que dos colecciones distintas (y no una sola con vectores nombrados) es
la forma correcta de convivir dos espacios vectoriales no comparables
(texto vs. imagen) sin arriesgar una fusion sin sentido entre ambos
(riesgo ya senalado en la Ronda 36 para RRF)."""


def best_relevance_score(scores: Iterable[float]) -> Optional[float]:
    """El mejor (mas alto) score de una coleccion de resultados, o
    None si esta vacia. Se mantiene aqui, y no como metodo de
    SemanticSearchResult (que vive en application), para que tanto la
    capa de aplicacion como pruebas de dominio puedan usarlo sin
    depender de una capa superior."""
    values = list(scores)
    return max(values) if values else None


def has_low_relevance(scores: Iterable[float], min_score: float = DEFAULT_MIN_RELEVANT_SCORE) -> bool:
    """True si hay resultados pero ninguno alcanza el umbral minimo de
    relevancia. Una lista vacia no cuenta como "baja relevancia" -- es
    "sin resultados", un caso ya manejado por separado (ver
    SemanticSearch.execute / IngestionPanel._refresh_search_results)."""
    best = best_relevance_score(scores)
    return best is not None and best < min_score


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno pura (sin numpy ni dependencias externas) --
    misma metrica que usa QdrantLocalVectorStore (Distance.COSINE), asi
    que los scores calculados aqui son comparables en naturaleza a los
    de la busqueda real, aunque se calculen por separado. Pensada para
    el comparador de modelos de embeddings (A vs B, ver
    application.rag.queries.compare_embedding_profiles): comparar dos
    perfiles no necesita un indice Qdrant persistido -- con la
    cantidad de fragmentos que maneja un proyecto tipico, un barrido
    lineal en memoria es instantaneo y evita tener que versionar
    IndexInfo/VectorStore por perfil (ADR-001, seccion 5), que es un
    cambio mucho mas invasivo reservado para cuando de verdad haga
    falta mantener varios indices reales en paralelo.

    Devuelve 0.0 si algun vector es todo ceros (evita division entre
    cero) en vez de lanzar una excepcion -- un vector nulo no tiene
    direccion, asi que "sin similitud" es la respuesta mas razonable."""
    if len(a) != len(b):
        raise ValueError(f"Los vectores deben tener la misma dimension ({len(a)} != {len(b)})")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class IndexInfo(BaseModel):
    """Un registro por proyecto (upsert), igual convencion que
    FragmentationPolicy/ExtractionRecord: guarda el estado vigente del
    indice, no su historial."""

    project_id: str
    embedding_provider: str
    embedding_model: str
    dimensions: int
    points_count: int = 0
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("dimensions")
    @classmethod
    def _dimensiones_positivas(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("dimensions debe ser mayor que cero")
        return v

    @field_validator("points_count")
    @classmethod
    def _puntos_no_negativos(cls, v: int) -> int:
        if v < 0:
            raise ValueError("points_count no puede ser negativo")
        return v


class VectorPoint(BaseModel):
    """Un punto a insertar en el VectorStore. id debe ser un UUID
    valido o un entero (restriccion del motor Qdrant); Chunk.id ya es
    un UUID, asi que se usa directamente sin traduccion."""

    id: str
    vector: list[float]
    payload: dict[str, object] = Field(default_factory=dict)


class VectorSearchHit(BaseModel):
    """Resultado crudo de VectorStore.search: solo el id del punto
    (== Chunk.id), el score de similitud y el payload guardado. La
    capa application lo une con el Chunk real (texto completo) via
    ChunkRepository -- el VectorStore es un indice, no la fuente de
    verdad del contenido."""

    chunk_id: str
    score: float
    payload: dict[str, object] = Field(default_factory=dict)
