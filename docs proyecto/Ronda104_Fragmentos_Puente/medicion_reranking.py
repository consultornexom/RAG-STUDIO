"""Ronda 104b -- costo del reranking (alternativa A vs B): carga del modelo,
memoria residente, latencia por consulta del Simulador (mismo motor que
POST /messages) con y sin cross-encoder, sobre las 14 consultas de LOTE01.

Las cifras dependen del equipo: sirven para comparar A contra B en la MISMA
máquina, no como valores absolutos de producción.

Uso: python3 medicion_reranking.py [--repeticiones 3]
"""
from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
for p in (RAIZ, RAIZ / "tests" / "integration", RAIZ / "tests" / "unit" / "application",
          RAIZ / "docs proyecto" / "Ronda102_Diagnostico_Simulador"):
    sys.path.insert(0, str(p))


def rss_mb() -> float:
    try:
        for linea in Path("/proc/self/status").read_text().splitlines():
            if linea.startswith("VmRSS:"):
                return int(linea.split()[1]) / 1024
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()
    import evaluacion_simulador as ev
    import test_ronda102_lote01_simulador as base
    from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker

    simuladores, _ = getattr(base.corpus, "__wrapped__", base.corpus)()
    resultado: dict = {"rss_mb_antes_de_cargar_reranker": round(rss_mb(), 1)}
    reranker = FastEmbedReranker(cache_dir=base.MODELOS)
    t0 = time.perf_counter()
    reranker.score("calentamiento", ["texto de prueba"])
    resultado["carga_reranker_s"] = round(time.perf_counter() - t0, 2)
    resultado["rss_mb_despues_de_cargar_reranker"] = round(rss_mb(), 1)
    tamano = sum(f.stat().st_size for f in (base.MODELOS / "models--Xenova--ms-marco-MiniLM-L-6-v2").rglob("*")
                 if f.is_file() and not f.is_symlink())
    resultado["modelo_reranker_mb_en_disco"] = round(tamano / 1e6, 1)

    for variante in ("sin", "con"):
        sim = simuladores[variante]
        for _, _, consulta, _, _ in ev.CASOS:  # calentamiento
            sim.execute(base.P, consulta, {}, limit=5)
        tiempos = []
        for _ in range(a.repeticiones):
            for _, _, consulta, _, _ in ev.CASOS:
                t0 = time.perf_counter()
                sim.execute(base.P, consulta, {}, limit=5)
                tiempos.append((time.perf_counter() - t0) * 1000)
        tiempos.sort()
        resultado[f"{variante}_reranking_ms"] = {
            "n": len(tiempos), "p50": round(statistics.median(tiempos), 1),
            "p95": round(tiempos[int(0.95 * (len(tiempos) - 1))], 1), "max": round(tiempos[-1], 1),
        }
    candidatos = ["texto " * 120] * 40
    t0 = time.perf_counter()
    reranker.score("¿Qué documentos necesito para entrar al bachillerato?", candidatos)
    resultado["reranker_40_candidatos_largos_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    print(json.dumps(resultado, indent=1, ensure_ascii=False))
    if a.salida:
        a.salida.write_text(json.dumps(resultado, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
