# -*- coding: utf-8 -*-
"""Punto de entrada del benchmark A/B de la Fase -1 de RAG 4. Corre las
94 preguntas de corpus_preguntas.json contra Sistema A (determinista) y
Sistema B (planificador LLM local vía Ollama) sobre el MISMO snapshot
del proyecto piloto, con Shadow Retrieval al 100% (sección 6 del
documento de decisión RAG4: durante la certificación -- que es
exactamente lo que es esta Fase -1 -- se corre siempre en paralelo, no
por muestreo).

Registra la huella de ejecución obligatoria de la sección 4 en un JSONL
(un renglón por pregunta), con TODOS los campos no negociables:
query_id, project_id, index_snapshot_id, retrieval_strategy,
planner_model_id, planner_model_version/hash, prompt_template_hash,
temperature, top_p, max_hops, generated_subqueries, selected_sources,
retrieval_parameters, retrieved_chunk_ids, scores, reranker_version,
latency, token_usage.

Uso (ver README_ejecutar_localmente.md para el detalle completo):
    python run_benchmark.py --snapshot-dir ./trabajo/piloto_b --ollama-model llama3.2:3b
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness import build_rag_service
from ollama_client import OllamaClient
from sistema_a import run_sistema_a
from sistema_b_planificador import run_sistema_b


def cargar_corpus(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def registro_auditoria(query_id: str, project_id: str, index_snapshot_id: str, resultado, reranker_version: str | None) -> dict:
    """Un renglón de la huella de ejecución -- mismo formato para
    Sistema A y Sistema B, para poder comparar de verdad (sección 4 del
    documento de decisión RAG4: campo no negociable desde la Fase -1)."""
    return {
        "query_id": query_id,
        "project_id": project_id,
        "index_snapshot_id": index_snapshot_id,
        "system": resultado.system,
        "retrieval_strategy": [t.retrieval_strategy for t in resultado.trace],
        "planner_model_id": resultado.planner_model_id,
        "planner_model_version": resultado.planner_model_version,
        "prompt_template_hash": resultado.prompt_template_hash,
        "temperature": resultado.temperature,
        "top_p": resultado.top_p,
        "max_hops": resultado.max_hops,
        "generated_subqueries": resultado.generated_subqueries,
        "selected_sources": sorted({sid for t in resultado.trace for sid in t.source_ids}),
        "retrieval_parameters": [{"query": t.query, "top_k": t.top_k} for t in resultado.trace],
        "retrieved_chunk_ids": [t.retrieved_chunk_ids for t in resultado.trace],
        "scores": [t.scores for t in resultado.trace],
        "reranker_version": reranker_version,
        "latency_ms": resultado.total_latency_ms,
        "num_retrievals": resultado.num_retrievals,
        "token_usage": resultado.token_usage,
        "error": resultado.error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True, help="Carpeta ya preparada por preparar_proyecto_piloto.py")
    parser.add_argument("--runtime-scratch-dir", default="./trabajo/_runtime_scratch")
    parser.add_argument("--corpus", default="corpus_preguntas.json")
    parser.add_argument("--ollama-model", required=True, help="Nombre del modelo ya descargado con 'ollama pull', p. ej. llama3.2:3b")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default="resultados_benchmark.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="Solo correr las primeras N preguntas (para una prueba rápida antes de la corrida completa)")
    args = parser.parse_args()

    print("Construyendo RagService real contra el snapshot piloto (nunca 'AGENTE UDL')...")
    rag_service, project_id = build_rag_service(args.snapshot_dir, args.runtime_scratch_dir)
    index_snapshot_id = Path(args.snapshot_dir).name  # identificador simple y suficiente para este prototipo aislado

    ollama = OllamaClient(model=args.ollama_model, host=args.ollama_host)

    corpus = cargar_corpus(Path(args.corpus))
    if args.limit:
        corpus = corpus[: args.limit]
    print(f"Corriendo {len(corpus)} preguntas (Shadow Retrieval 100%: Sistema A y B en cada una)...")

    with open(args.out, "w", encoding="utf-8") as f:
        for i, pregunta in enumerate(corpus, start=1):
            print(f"[{i}/{len(corpus)}] {pregunta['id']} ({pregunta['category']}): {pregunta['query_text'][:80]}")

            resultado_a = run_sistema_a(rag_service, project_id, pregunta["query_text"], top_k=args.top_k)
            f.write(json.dumps({
                **registro_auditoria(pregunta["id"], project_id, index_snapshot_id, resultado_a, reranker_version=None),
                "category": pregunta["category"],
                "query_text": pregunta["query_text"],
                "gold_evidence": pregunta["gold_evidence"],
            }, ensure_ascii=False) + "\n")

            resultado_b = run_sistema_b(
                rag_service, project_id, pregunta["query_text"], ollama,
                max_hops=args.max_hops, top_k=args.top_k,
            )
            f.write(json.dumps({
                **registro_auditoria(pregunta["id"], project_id, index_snapshot_id, resultado_b, reranker_version=None),
                "category": pregunta["category"],
                "query_text": pregunta["query_text"],
                "gold_evidence": pregunta["gold_evidence"],
            }, ensure_ascii=False) + "\n")

            if resultado_b.error:
                print(f"    AVISO Sistema B: {resultado_b.error}")

    print(f"\nListo. {len(corpus)} preguntas x 2 sistemas = {len(corpus)*2} renglones en {args.out}")
    print("Siguiente paso: Actividad 4 (analizar_resultados.py) para agregar métricas por categoría.")


if __name__ == "__main__":
    sys.exit(main())
