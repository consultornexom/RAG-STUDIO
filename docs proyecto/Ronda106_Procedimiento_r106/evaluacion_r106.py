"""Ronda 106 -- evaluación del procedimiento r106 implementado (motor real,
SimulateConversation) contra r105b, con los 14 casos de LOTE01, los cinco
archivos reales, la intención real de requisitos de AGENTE UDL y los modelos
reales. Compara con lo medido por el prototipo en la Ronda 105f
(../Ronda105c_Diagnostico_Post_P1/resultados_intencion_real.json, variante VYR).

Uso: python3 evaluacion_r106.py [--compartidos documento_completo|por_encabezado|por_tamanio_todos|sintetico]
                                [--contador palabras|subpalabras] [--salida resultados.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests" / "integration"))

import test_ronda106_procedimiento_r106 as t  # noqa: E402


def contador_subpalabras():
    from tokenizers import Tokenizer

    from domain.ingestion.ports import TokenCounter

    ruta = next((RAIZ / "data" / "models").glob(
        "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots/*/tokenizer.json"))
    tok = Tokenizer.from_file(str(ruta))
    tok.no_truncation()

    class Contador(TokenCounter):
        def count_tokens(self, text: str) -> int:
            return len(tok.encode(text, add_special_tokens=False).ids)

    return Contador()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compartidos", default="documento_completo")
    ap.add_argument("--contador", default="palabras", choices=["palabras", "subpalabras"])
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()
    contador = contador_subpalabras() if a.contador == "subpalabras" else None
    if a.compartidos == "sintetico":
        sims, titulo_de = t.construir("documento_completo", documentos=t.SINTETICO, token_counter=contador)
        casos = [c for c in t.CASOS if c[0] == "R1"]
    else:
        sims, titulo_de = t.construir(a.compartidos, token_counter=contador)
        casos = t.CASOS
    res = t.evaluar(sims, titulo_de, casos)
    clave = f"{a.compartidos}+{a.contador}"
    salida = {}
    for proc in ("r105b", "r106"):
        pos = {cid: p for cid, (p, _d, _t) in res[proc].items()}
        salida[f"{clave}|{proc}"] = {
            "MRR": round(t.mrr(res[proc]), 3), "posiciones": pos,
            "decisiones": {cid: [d[0], d[1], round(d[2], 4), d[3]] for cid, (_p, d, _t) in res[proc].items()},
        }
        print(f"{clave:36} {proc:6} MRR {t.mrr(res[proc]):.3f}  " + " ".join(f"{c}={p}" for c, p in pos.items()))
    iguales = all(res["r105b"][c][1] == res["r106"][c][1] for c in res["r105b"])
    print(f"{'':36} decisiones idénticas r105b/r106: {iguales}")
    for cid in ("R1", "R2"):
        if cid not in res["r106"]:
            continue
        trace = res["r106"][cid][2]
        print(f"  r106 {cid}: " + " | ".join(
            f"{i}. {titulo_de[r.chunk.source_id][:26]} búsq#{o.retrieval_rank} afin {o.affinity:.2f}"
            + (" (por referencia)" if o.referenced_from else "")
            for i, (r, o) in enumerate(zip(trace.search_results, trace.result_ordering, strict=True), 1)))
    if a.salida:
        previo = json.loads(a.salida.read_text()) if a.salida.exists() else {}
        previo.update(salida)
        a.salida.write_text(json.dumps(previo, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
