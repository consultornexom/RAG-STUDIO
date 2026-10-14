"""Comparador de modelos de embeddings (A vs B) -- ver ADR-001, sección
5, y bitácora del proyecto sobre el experimento asimétrico. Responde a
la pregunta "¿este modelo encuentra mejor mis fragmentos que aquel
otro?" corriendo la misma consulta contra dos perfiles distintos, sin
tener que correr un script aparte (como se hizo con
`experimento_modelo_asimetrico.py`, dos instalaciones separadas en
carpetas temporales).

Decisión de alcance deliberada: esto calcula todo en memoria bajo
demanda (similitud coseno pura, `domain.rag.entities.cosine_similarity`)
sobre los fragmentos ya guardados por `ChunkRepository` -- NO usa
`VectorStore` ni persiste un segundo índice paralelo. Mantener dos
índices Qdrant reales simultáneos por proyecto (uno por perfil)
exigiría versionar `IndexInfo`/`VectorStore` (la "matriz completa de
EmbeddingModelConfig/Index" que menciona ADR-001, sección 5) -- un
cambio de arquitectura mucho más invasivo que no está justificado solo
para comparar interactivamente un par de consultas. Con la cantidad de
fragmentos de un proyecto típico, un barrido lineal en memoria es
prácticamente instantáneo."""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from domain.ingestion.entities import Chunk
from domain.ingestion.ports import ChunkRepository
from domain.rag.entities import cosine_similarity
from domain.rag.ports import EmbeddingProvider


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class ProfileComparisonResult(BaseModel):
    """Resultado de un perfil dentro de la comparación: qué modelo se
    usó (para mostrarlo en la UI, igual que `IndexInfo`) y sus mejores
    resultados para la consulta."""

    profile: str
    provider_name: str
    model_name: str
    dimensions: int
    results: list[ScoredChunk]


class CompareEmbeddingProfiles:
    def __init__(
        self,
        chunk_repository: ChunkRepository,
        provider_factory: Callable[[str], EmbeddingProvider],
    ):
        """provider_factory: construye un EmbeddingProvider a partir de
        un nombre de perfil corto (p. ej. "simetrico"). Se recibe como
        callable, no como import directo de
        infrastructure.embeddings.fastembed_provider.make_provider_for_profile,
        para que esta query de application no dependa de infrastructure
        (ADR-001, sección 4) -- app/bootstrap.py es quien la conecta."""
        self._chunks = chunk_repository
        self._provider_factory = provider_factory

    def execute(
        self, project_id: str, query_text: str, profile_a: str, profile_b: str,
        source_id: Optional[str] = None, limit: int = 5,
    ) -> tuple[ProfileComparisonResult, ProfileComparisonResult]:
        if not query_text.strip():
            raise ValueError("La consulta de comparación no puede estar vacía")
        chunks = (
            self._chunks.list_for_source(project_id, source_id) if source_id
            else self._chunks.list_for_project(project_id)
        )
        return (
            self._compare_one(profile_a, query_text, chunks, limit),
            self._compare_one(profile_b, query_text, chunks, limit),
        )

    def _compare_one(
        self, profile: str, query_text: str, chunks: list[Chunk], limit: int,
    ) -> ProfileComparisonResult:
        provider = self._provider_factory(profile)
        query_vector = provider.embed_query(query_text)
        vectors = provider.embed_texts([chunk.text for chunk in chunks]) if chunks else []
        scored = [
            ScoredChunk(chunk=chunk, score=cosine_similarity(query_vector, vector))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return ProfileComparisonResult(
            profile=profile, provider_name=provider.provider_name, model_name=provider.model_name,
            dimensions=provider.dimensions, results=scored[:limit],
        )
