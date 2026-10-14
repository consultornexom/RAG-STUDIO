# -*- coding: utf-8 -*-
"""Sistema A: RAG STUDIO tal como existe hoy (determinista) -- una sola
llamada a RagService.search_hybrid, sin ningún LLM de por medio. Ver
sección 10.3 del documento de decisión RAG4."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RetrievalTraceEntry:
    """Un renglón de la huella de ejecución obligatoria (sección 4 del
    documento de decisión RAG4) -- los mismos campos para Sistema A y
    Sistema B, para poder comparar de verdad."""
    retrieval_strategy: str
    query: str
    top_k: int
    retrieved_chunk_ids: list[str]
    scores: list[float]
    source_ids: list[str]
    latency_ms: float


@dataclass
class SystemResult:
    system: str  # "A" o "B"
    trace: list[RetrievalTraceEntry] = field(default_factory=list)
    num_retrievals: int = 0
    total_latency_ms: float = 0.0
    planner_model_id: str = "ninguno (Sistema A es determinista)"
    planner_model_version: str = "n/a"
    prompt_template_hash: str = "n/a"
    temperature: float = 0.0
    top_p: float = 1.0
    max_hops: int = 1
    generated_subqueries: list[str] = field(default_factory=list)
    token_usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    error: str | None = None


def run_sistema_a(rag_service, project_id: str, query_text: str, top_k: int = 5) -> SystemResult:
    start = time.monotonic()
    try:
        results = rag_service.search_hybrid(project_id, query_text, limit=top_k)
    except Exception as exc:  # noqa: BLE001 -- se registra el error, no se detiene el benchmark completo
        return SystemResult(system="A", error=f"{type(exc).__name__}: {exc}")
    latency_ms = (time.monotonic() - start) * 1000
    entry = RetrievalTraceEntry(
        retrieval_strategy="hybrid_search",
        query=query_text,
        top_k=top_k,
        retrieved_chunk_ids=[r.chunk.id for r in results],
        scores=[r.score for r in results],
        source_ids=[r.chunk.source_id for r in results],
        latency_ms=latency_ms,
    )
    return SystemResult(
        system="A", trace=[entry], num_retrievals=1, total_latency_ms=latency_ms,
        generated_subqueries=[query_text],
    )
