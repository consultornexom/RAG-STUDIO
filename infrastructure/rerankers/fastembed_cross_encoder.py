"""Adaptador Reranker sobre el paquete `fastembed` (modelo ONNX local,
el mismo paquete que ya usa infrastructure.embeddings.fastembed_provider
-- no se agrega ninguna dependencia nueva al proyecto). Implementa el
puerto domain.rag.ports.Reranker.

ADR-003, Pista A.2: "reranking real: nuevo puerto/adaptador de
reranking local (cross-encoder ligero, mismo patrón de puerto/adaptador
que CachingEmbeddingProvider), conectado después de la fusión RRF,
opcional por proyecto" -- este es ese adaptador.

Modelo por defecto: "Xenova/ms-marco-MiniLM-L-6-v2" (~0.08 GB) -- el
modelo insignia de fastembed.rerank.cross_encoder.TextCrossEncoder,
bien establecido para reranking de propósito general. Se eligió (en
vez de un modelo más grande como BAAI/bge-reranker-v2-m3) por el mismo
criterio que ya aplicó fastembed_provider.py al descartar el modelo
asimétrico e5-large como default: "ligero" y "sin tareas pesadas" son
restricciones explícitas del proyecto (ADR-001), no solo del modelo de
embeddings.

Misma limitación que FastEmbedEmbeddingProvider (ver ese módulo): el
modelo se descarga de Hugging Face la primera vez que se usa; sin
conexión a internet en ese primer uso, `score` lanza RerankerError --
no hay modo completamente offline "desde cero" todavía, igual que el
proveedor de embeddings.

`TextCrossEncoder.rerank(query, documents)` (fastembed >= 0.4) devuelve
los puntajes EN EL MISMO ORDEN que `documents` -- a pesar del nombre,
no reordena nada por sí solo; quien reordena con esos puntajes es
`application.rag.queries.hybrid_search.HybridSearch.execute`, no este
adaptador (mismo reparto de responsabilidades que EmbeddingProvider:
domain/infrastructure calculan, application decide qué hacer con el
resultado)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from domain.rag.exceptions import RerankerError
from domain.rag.ports import Reranker

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

_DEFAULT_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class FastEmbedReranker(Reranker):
    def __init__(self, model_name: str = _DEFAULT_MODEL, cache_dir: Optional[str | Path] = None):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir is not None else None
        # Carga perezosa: no se descarga nada hasta el primer score()
        # (mismo criterio que FastEmbedEmbeddingProvider._ensure_loaded).
        self._model: Optional["TextCrossEncoder"] = None

    def _ensure_loaded(self) -> "TextCrossEncoder":
        if self._model is not None:
            return self._model
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as exc:
            raise RerankerError(
                "El paquete 'fastembed' no esta instalado. Agrega la dependencia "
                "declarada en pyproject.toml/requirements.txt e instala de nuevo."
            ) from exc
        try:
            self._model = TextCrossEncoder(model_name=self._model_name, cache_dir=self._cache_dir)
        except Exception as exc:
            raise RerankerError(
                f"No se pudo cargar el modelo de reranking {self._model_name!r}. "
                f"La primera vez requiere descargarlo de Hugging Face: revisa la "
                f"conexion a internet. Detalle original: {exc}"
            ) from exc
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(self, query_text: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        model = self._ensure_loaded()
        try:
            return list(model.rerank(query_text, passages))
        except Exception as exc:
            raise RerankerError(
                f"El modelo de reranking {self._model_name!r} fallo al calcular "
                f"puntajes: {exc}"
            ) from exc
