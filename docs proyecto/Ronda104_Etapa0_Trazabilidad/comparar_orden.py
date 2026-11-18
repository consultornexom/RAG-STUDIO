"""Ronda 104b, Etapa 0 -- prueba de aceptación 1: la misma consulta con la
misma configuración produce el mismo orden de fragmentos antes y después de
la Etapa 0.

Ejecuta las 14 consultas de LOTE01 (cinco archivos reales, modelos reales)
con el motor del código indicado y guarda, por consulta y por configuración
de reranking, la acción, la intención y la lista ORDENADA de fragmentos
entregados como (fuente, sha256 del texto, puntaje redondeado a 6
decimales). Los ids de fragmento cambian en cada construcción en memoria,
por eso se compara por contenido.

Uso:
  python3 comparar_orden.py --codigo <raíz del código> --rerank sin|con --salida orden.json [--casos R1,R2]
  python3 comparar_orden.py --comparar antes.json despues.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_DOCS = AQUI.parents[1]


def _canonico(registro):
    """Ronda 105b: fragmentos con el MISMO texto en fuentes distintas (p. ej.
    la sección «Información compartida…» de dos planes) empatan y, en esta
    construcción en memoria con ids aleatorios, su orden relativo y sus
    puntajes RRF pueden alternar entre ejecuciones del MISMO código. Se
    comparan como grupo: posiciones consecutivas con la misma huella de
    texto se reducen a (huella, fuentes ordenadas), sin puntaje."""
    if not registro:
        return registro
    grupos, i, fr = [], 0, registro["fragmentos"]
    while i < len(fr):
        j = i
        while j + 1 < len(fr) and fr[j + 1][1] == fr[i][1]:
            j += 1
        grupos.append(fr[i] if i == j else [sorted(f[0] for f in fr[i:j + 1]), fr[i][1]])
        i = j + 1
    return {**registro, "fragmentos": grupos}


def comparar(a: Path, b: Path, canonico: bool = True) -> int:
    x, y = json.loads(a.read_text()), json.loads(b.read_text())
    diferencias = []
    for clave in sorted(set(x) | set(y)):
        vx, vy = (_canonico(x.get(clave)), _canonico(y.get(clave))) if canonico else (x.get(clave), y.get(clave))
        if vx != vy:
            diferencias.append(clave)
    print(f"{len(set(x) & set(y))} consultas comparadas; diferencias: {diferencias or 'ninguna'}")
    return 1 if diferencias else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", type=Path)
    ap.add_argument("--rerank", choices=["con", "sin"])
    ap.add_argument("--casos", default="")
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--comparar", nargs=2, type=Path)
    a = ap.parse_args()
    if a.comparar:
        return comparar(*a.comparar)
    raiz = a.codigo.resolve()
    # El código evaluado va primero en la ruta; las pruebas y el arnés de
    # la Ronda 102 se toman del repositorio de documentación.
    for p in (RAIZ_DOCS / "docs proyecto" / "Ronda102_Diagnostico_Simulador", RAIZ_DOCS / "tests" / "integration",
              raiz / "tests" / "unit" / "application", raiz):
        sys.path.insert(0, str(p))
    import evaluacion_simulador as ev
    import test_ronda102_lote01_simulador as base

    simuladores, titulo_de = getattr(base.corpus, "__wrapped__", base.corpus)()
    sim = simuladores[a.rerank]
    elegidos = set(filter(None, a.casos.split(",")))
    datos = json.loads(a.salida.read_text()) if a.salida and a.salida.exists() else {}
    for cid, _g, consulta, _f, _t in ev.CASOS:
        if elegidos and cid not in elegidos:
            continue
        trace = sim.execute(base.P, consulta, {}, limit=5)
        datos[f"{a.rerank}|{cid}"] = {
            "accion": trace.action.value, "intencion": trace.matched_intent_name,
            "confianza": round(trace.confidence, 6),
            "fragmentos": [[titulo_de[r.chunk.source_id], hashlib.sha256(r.chunk.text.encode()).hexdigest()[:16],
                            round(r.score, 6)] for r in trace.search_results],
        }
    if a.salida:
        a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
    print(f"{len(datos)} consultas guardadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
