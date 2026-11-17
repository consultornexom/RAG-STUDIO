"""Ronda 104b -- medición del diseño Y/R (prototipo_referencias.py) sobre las
14 consultas de la Ronda 102 con los cinco archivos reales de LOTE01.

Reproduce los pasos de SimulateConversation._search_and_filter (fuentes
permitidas por filtros, pool de 20, afinidad combinada por RRF) y compara:

  base   código actual (Ronda 102)
  Y      afinidad 0 para fragmentos solo-YAML
  R      resolución de referencias, modo "pool" (destino ya en candidatos)
  YR     Y + R (modo pool)  <- propuesta
  YRb    Y + R modo "busqueda" (destino buscado dentro de la fuente referida)
  YR2    Y + R modo pool con hasta 2 destinos por fuente referida (máx. 5)

Métricas por consulta: posición del fragmento correcto en el top 5 final;
"puente_delante": un puente que remite a la fuente esperada aparece antes
que el fragmento correcto (o el correcto no aparece); "solo_yaml": número de
fragmentos sin contenido (solo encabezado YAML) en el top 5; latencia (ms)
del paso posterior a la búsqueda.

Estos resultados son de la REPRODUCCIÓN CON SUPUESTOS (intenciones y
metadatos de la Ronda 102), no del incidente real.

Uso: python3 evaluacion_y_r.py --compartidos documento_completo|por_encabezado --rerank con|sin
     [--casos R1,R2] --salida resultados_y_r.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
for p in (RAIZ, RAIZ / "tests" / "integration", RAIZ / "tests" / "unit" / "application",
          RAIZ / "docs proyecto" / "Ronda102_Diagnostico_Simulador", AQUI):
    sys.path.insert(0, str(p))

VARIANTES = ["base", "Y", "R", "YR", "YRb"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compartidos", choices=["documento_completo", "por_encabezado"], required=True)
    ap.add_argument("--rerank", choices=["con", "sin"], required=True)
    ap.add_argument("--casos", default="")
    ap.add_argument("--variantes", default=",".join(VARIANTES))
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()

    import evaluacion_simulador as ev
    import prototipo_referencias as pr
    import test_ronda102_lote01_simulador as base
    from domain.conversational.section_affinity import SectionAffinity, affinity_title, combine_with_retrieval
    from domain.ingestion.entities import FragmentationStrategy

    if a.compartidos == "por_encabezado":
        original = base.IngestionService.set_fragmentation_policy

        def politica(self, project_id, tipo, **kw):
            if tipo in ("informacion_admisiones", "informacion_academica"):
                kw = dict(strategy=FragmentationStrategy.POR_ENCABEZADO, target_tokens=500, overlap_tokens=60,
                          min_tokens=80)
            return original(self, project_id, tipo, **kw)

        base.IngestionService.set_fragmentation_policy = politica

    simuladores, titulo_de = getattr(base.corpus, "__wrapped__", base.corpus)()
    sim = simuladores[a.rerank]
    rag, P = sim._rag, base.P
    fuentes = sim._sources.list_for_project(P)
    variables = sim._variables.list_for_project(P)
    intents = sim._intents.list_for_project(P)
    nombre_a_id = {titulo: sid for sid, titulo in titulo_de.items()}

    def titulo(chunk, con_y):
        if con_y and not chunk.section_title and pr.solo_yaml(chunk.text):
            return ""
        return affinity_title(chunk.section_title, chunk.text, titulo_de[chunk.source_id])

    def ejecutar(consulta, variante):
        trace = sim.execute(P, consulta, {}, limit=5)
        if trace.action.value != "responder" or not trace.applied_metadata_filters:
            return trace.search_results, {}, 0.0
        permitidas = {s.id: s.title for s in fuentes if sim._source_matches_filters(
            P, s.id, variables, trace.applied_metadata_filters)}
        texto = trace.retrieval_query or consulta
        pool = rag.search_hybrid(P, texto, limit=20, only_usable_sources=True, rerank=rag.has_reranker,
                                 source_ids=set(permitidas))
        t0 = time.perf_counter()
        enlaces: dict = {}
        if "R" in variante:
            modo = "busqueda" if variante.endswith("b") else "pool"
            pr.MAX_POR_FUENTE = 2 if variante.endswith("2") else 1
            pr.MAX_DESTINOS = 5 if variante.endswith("2") else 3
            res = pr.resolver_referencias(
                pool, permitidas, modo=modo,
                buscar_en_fuente=lambda sid: rag.search_hybrid(P, texto, limit=3, only_usable_sources=True,
                                                               rerank=rag.has_reranker, source_ids={sid}))
            pool, enlaces = res.candidatos, res.enlaces
        intent = next(i for i in intents if i.name == trace.matched_intent_name)
        afinidad = SectionAffinity(intent, intents, consulta, sim._catalog_mention_masker(P))
        puntajes = [afinidad.score(titulo(r.chunk, "Y" in variante)) for r in pool]
        orden = [pool[i].chunk.id for i in combine_with_retrieval(puntajes)]
        if enlaces:
            orden = pr.aplicar_restriccion(orden, enlaces)
        por_id = {r.chunk.id: r for r in pool}
        return [por_id[c] for c in orden[:5]], enlaces, (time.perf_counter() - t0) * 1000

    elegidos = set(filter(None, a.casos.split(",")))
    clave = f"{a.compartidos}|{a.rerank}"
    datos = json.loads(a.salida.read_text()) if a.salida and a.salida.exists() else {}
    for variante in a.variantes.split(","):
        filas = datos.setdefault(clave, {}).setdefault(variante, {})
        for cid, _grupo, consulta, fuente, texto in ev.CASOS:
            if elegidos and cid not in elegidos:
                continue
            final, enlaces, ms = ejecutar(consulta, variante)
            pos = next((i for i, r in enumerate(final, 1)
                        if titulo_de[r.chunk.source_id] == fuente and texto in r.chunk.text), None)
            puente = next((i for i, r in enumerate(final, 1)
                           if pr.palabras_sin_yaml(r.chunk.text) <= pr.MAX_PALABRAS_PUENTE
                           and nombre_a_id[fuente] in pr.detectar_referencias(
                               r.chunk.text, r.chunk.source_id, pr.indice_de_nombres(titulo_de))[0]), None)
            filas[cid] = {
                "pos": pos,
                "puente_delante": puente is not None and (pos is None or puente < pos),
                "solo_yaml": sum(1 for r in final if pr.solo_yaml(r.chunk.text)),
                "destinos": len(enlaces), "ms_post": round(ms, 2),
            }
        n = len(filas)
        mrr = sum(1 / f["pos"] for f in filas.values() if f["pos"]) / n
        r1 = sum(1 for f in filas.values() if f["pos"] == 1) / n
        print(f"{clave:24} {variante:5} n={n:2} R@1 {r1:.2f} MRR {mrr:.3f} "
              f"puente_delante={sum(f['puente_delante'] for f in filas.values())} "
              f"solo_yaml={sum(f['solo_yaml'] for f in filas.values())}  "
              + " ".join(f"{c}={f['pos']}" for c, f in filas.items()))
    if a.salida:
        a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
