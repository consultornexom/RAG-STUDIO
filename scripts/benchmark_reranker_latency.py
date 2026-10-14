#!/usr/bin/env python3
"""Benchmark de latencia real del reranker (ADR-003, Pista C.4 -- ver
docs proyecto/RAG_STUDIO_Propuesta_C4_Aprendizaje_Retrieval.docx,
Opción 1).

Por qué existe este script: la decisión del consultor sobre activar
FastEmbedReranker por defecto en la vía de producción fue condicional
-- "en caso de que realmente le dé valor a RAG Studio... y se mide
antes su costo real de latencia, entonces sí". Esa medición no se pudo
hacer durante el diseño porque el entorno de verificación usado en esa
ronda no tiene acceso a Hugging Face (el modelo del reranker,
"Xenova/ms-marco-MiniLM-L-6-v2", nunca se descargó ahí y la red está
bloqueada) -- ver Validacion_observaciones_RAG_STUDIO.md, Ronda 38.

Este script está pensado para correr en una máquina con acceso real a
internet (típicamente la del propio consultor, o cualquier entorno
donde ya se hayan usado embeddings/reranking reales antes). La primera
vez que corra, fastembed descargará el modelo del reranker a
data/models/ igual que ya hace con los modelos de embeddings -- ese
costo de descarga (~0.08 GB) es aparte de la latencia que este script
mide, que es solo el costo de PUNTAJE por consulta una vez que el
modelo ya está cargado en memoria.

Uso:
    python scripts/benchmark_reranker_latency.py <project_id> [--repeats 3] [--limit 5]

Si se omite <project_id>, el script lista los proyectos existentes
(id y nombre) en vez de fallar con el mensaje genérico de argparse --
así no hace falta ir a buscar el id a otro lado.

Si no se pasa ningún query_text explícito, reutiliza las consultas ya
curadas en el banco de pruebas de Calidad del proyecto (TestCase.
query_text) -- así el benchmark corre sobre consultas reales del
proyecto, no sobre texto inventado. Si el proyecto no tiene ningún caso
de prueba activo, se puede pasar un archivo de texto con una consulta
por línea vía --queries-file.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import bootstrap  # noqa: E402
from domain.rag.exceptions import RerankerError  # noqa: E402


def _load_queries(app_context, project_id: str, queries_file: str | None) -> list[str]:
    if queries_file:
        text = Path(queries_file).read_text(encoding="utf-8")
        queries = [line.strip() for line in text.splitlines() if line.strip()]
        if not queries:
            raise SystemExit(f"'{queries_file}' no contiene ninguna consulta no vacía.")
        return queries

    test_cases = app_context.quality_service.list_test_cases(project_id)
    queries = [tc.query_text for tc in test_cases if tc.active and tc.query_text.strip()]
    if not queries:
        raise SystemExit(
            "El proyecto no tiene casos de prueba activos con query_text para reutilizar. "
            "Pasa --queries-file con una consulta real por línea."
        )
    return queries


def _time_search(rag_service, project_id: str, query_text: str, limit: int, rerank: bool) -> float:
    started = time.perf_counter()
    rag_service.search_hybrid(project_id, query_text, limit=limit, rerank=rerank)
    return (time.perf_counter() - started) * 1000.0


def _print_available_projects(app_context) -> None:
    projects = app_context.project_service.list_projects()
    if not projects:
        print("No hay ningún proyecto todavía -- crea uno primero en RAG STUDIO.")
        return
    print("Falta indicar sobre qué proyecto medir. Proyectos disponibles:\n")
    for project in projects:
        print(f"  {project.id}   {project.name}")
    print(
        "\nVuelve a correr el script agregando uno de esos id, por ejemplo:\n"
        f"  python scripts/benchmark_reranker_latency.py {projects[0].id}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "project_id", nargs="?", default=None,
        help="id del proyecto ya indexado sobre el que medir -- si se omite, se listan los proyectos disponibles",
    )
    parser.add_argument("--repeats", type=int, default=3, help="repeticiones por consulta (default 3)")
    parser.add_argument("--limit", type=int, default=5, help="limit de search_hybrid (default 5, igual que el motor conversacional)")
    parser.add_argument("--queries-file", default=None, help="archivo con una consulta por línea (opcional)")
    args = parser.parse_args()

    print("Iniciando RAG STUDIO (bootstrap real, misma configuración que la app de escritorio)...")
    app_context = bootstrap()

    if args.project_id is None:
        _print_available_projects(app_context)
        return

    rag_service = app_context.rag_service

    queries = _load_queries(app_context, args.project_id, args.queries_file)
    print(f"{len(queries)} consulta(s), {args.repeats} repetición(es) cada una, limit={args.limit}.\n")

    print(
        "Primera búsqueda con rerank=True: si el modelo del reranker no está "
        "descargado todavía, fastembed lo descargará ahora desde Hugging Face "
        "(requiere red) -- puede tardar más que el resto por esta única vez."
    )

    sin_rerank_ms: list[float] = []
    con_rerank_ms: list[float] = []

    try:
        for query_text in queries:
            for _ in range(args.repeats):
                sin_rerank_ms.append(_time_search(rag_service, args.project_id, query_text, args.limit, rerank=False))
                con_rerank_ms.append(_time_search(rag_service, args.project_id, query_text, args.limit, rerank=True))
    except RerankerError as exc:
        raise SystemExit(
            "\nNo se pudo cargar el modelo del reranker -- normalmente por falta de "
            "acceso a Hugging Face en esta máquina (revisa tu conexión a internet; "
            "la primera vez necesita descargar el modelo). Detalle original:\n"
            f"  {exc}\n\n"
            "Sin el reranker cargado no se puede medir su costo real -- este script "
            "no reporta ningún número inventado. Vuelve a correrlo con acceso a "
            "internet."
        ) from exc

    def _resumen(nombre: str, valores: list[float]) -> None:
        ordenados = sorted(valores)
        p50 = statistics.median(ordenados)
        p95_index = min(len(ordenados) - 1, int(round(0.95 * (len(ordenados) - 1))))
        p95 = ordenados[p95_index]
        print(
            f"{nombre:22s} n={len(valores):<4d} "
            f"promedio={statistics.mean(valores):8.1f} ms   "
            f"p50={p50:8.1f} ms   p95={p95:8.1f} ms   max={max(valores):8.1f} ms"
        )

    print("\n--- Resultado ---")
    _resumen("Sin reranker (RRF solo)", sin_rerank_ms)
    _resumen("Con reranker real", con_rerank_ms)
    delta_p50 = statistics.median(con_rerank_ms) - statistics.median(sin_rerank_ms)
    print(f"\nCosto adicional del reranker (delta de p50): {delta_p50:+.1f} ms por consulta.")
    print(
        "\nEste número es el que la Opción 1 del documento C.4 pedía medir antes "
        "de decidir si activar el reranker por defecto en la vía de producción "
        "(SimulateConversation / POST /projects/{id}/messages) da valor real a "
        "RAG STUDIO, considerando esa latencia añadida por consulta."
    )


if __name__ == "__main__":
    main()
