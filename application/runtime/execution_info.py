"""Datos de ejecución de un turno (Ronda 104b, Etapa 0, autorizada por
NEXOM): con qué código, instantánea, índice, procedimiento de recuperación y
configuración efectiva de reranking se produjo una respuesta, con qué texto
y filtros se buscó, y qué fragmentos se entregaron en qué orden.

Un mismo registro (dict serializable) se guarda en runtime.db y se devuelve
en POST /messages (solo con la credencial operativa), para que NEXOM Testing
Agent pueda identificar la configuración real de cada evaluación.

`base` es la parte FIJA por proceso e instantánea (código, instantánea,
índice, disponibilidad del reranker); la arma quien construye el motor
(interfaces/api/runtime_context.py). Este módulo no hace E/S.

Nunca contiene credenciales, claves, tokens, rutas del servidor ni texto de
documentos: solo identificadores, versiones, huellas y parámetros.
Lo que no se pudo determinar va en `unknown` (nunca se inventa).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

EXECUTION_FORMAT_VERSION = 1


def _faltantes(prefijo: str, bloque: Optional[Mapping[str, Any]], campos: tuple[str, ...]) -> list[str]:
    if not bloque:
        return [prefijo]
    return [f"{prefijo}.{c}" for c in campos if bloque.get(c) is None]


def base_unknown(base: Optional[Mapping[str, Any]]) -> list[str]:
    base = base or {}
    desconocidos = []
    codigo = base.get("code")
    if not codigo:
        desconocidos.append("code")
    else:
        desconocidos += [f"code.{c}" for c in codigo.get("unknown", [])]
    desconocidos += _faltantes("snapshot", base.get("snapshot"), ("declared_fingerprint", "fingerprint_at_load"))
    desconocidos += _faltantes("index", base.get("index"), ("embedding_model",))
    return desconocidos


def failure_execution_record(base: Optional[Mapping[str, Any]]) -> dict:
    """Turno fallido: solo la parte fija (no hubo búsqueda)."""
    base = dict(base or {})
    return {
        "format_version": EXECUTION_FORMAT_VERSION,
        "code": base.get("code"), "snapshot": base.get("snapshot"), "index": base.get("index"),
        "retrieval_pipeline": base.get("retrieval_pipeline"),
        "unknown": base_unknown(base),
    }


def execution_record(base: Optional[Mapping[str, Any]], trace) -> dict:
    """Registro completo de un turno atendido. `trace` es un
    SimulationTrace (no se importa para no acoplar dominios)."""
    base = dict(base or {})
    orden = trace.result_ordering if len(trace.result_ordering) == len(trace.search_results) else []
    resultados = []
    for posicion, resultado in enumerate(trace.search_results, start=1):
        detalle = orden[posicion - 1] if orden else None
        resultados.append({
            "position": posicion,
            "chunk_id": resultado.chunk.id,
            "source_id": resultado.chunk.source_id,
            "score": resultado.score,
            # Sin reordenamiento conversacional, el puesto de la búsqueda es
            # la posición entregada.
            "retrieval_rank": detalle.retrieval_rank if detalle else posicion,
            "affinity": detalle.affinity if detalle else None,
            # Ronda 106 (r106, componente R): fragmentos puente que trajeron
            # este fragmento por delante de ellos (vacía si no aplica).
            "referenced_from": list(detalle.referenced_from) if detalle else [],
        })
    desconocidos = base_unknown(base)
    return {
        "format_version": EXECUTION_FORMAT_VERSION,
        "code": base.get("code"),
        "snapshot": base.get("snapshot"),
        "index": base.get("index"),
        "retrieval_pipeline": trace.retrieval_pipeline,
        "reranking": {
            "setting": trace.reranking_setting,
            "model_available": trace.reranking_available,
            "available_model": trace.reranking_available_model,
            # Ronda 105b (P1): estado del modelo y configuración efectiva en el Runtime.
            "model_status": trace.reranking_model_status,
            "effective_in_runtime": trace.runtime_effective_reranking,
            "applied": trace.reranking_applied,
            "model": trace.reranking_model,
            "note": trace.reranking_note,
        },
        "search_text": trace.search_text,
        "applied_filters": dict(trace.applied_metadata_filters),
        "excluded_sources": trace.excluded_by_metadata_filter,
        "affinity_ordering": trace.section_ordering,
        "ambiguous_references": list(getattr(trace, "ambiguous_references", []) or []),
        "results": resultados,
        "unknown": desconocidos,
    }
