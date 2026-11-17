"""Ronda 104 -- PROTOTIPO de medición (no modifica el motor): evalúa sobre
los 14 casos de la Ronda 102 (LOTE01 real) alternativas generales para los
fragmentos "puente" que solo remiten a otro documento del proyecto.

Reproduce los pasos de SimulateConversation._search_and_filter (fuentes
permitidas por filtros, pool de 20 con/sin reranking, afinidad combinada
por RRF -- Ronda 102) y aplica, por separado y combinadas:

  T  texto de búsqueda: si quitar los valores filtrados deja menos de 3
     palabras de contenido, se busca con la consulta original.
  Y  afinidad: un fragmento que solo contiene el encabezado YAML no toma el
     título de la fuente (afinidad 0); corrige un efecto de C2.
  P  afinidad por ruta: una sección toma la mayor afinidad entre su título
     y los de sus encabezados superiores (section_path, Ronda 100).
  R  referencias: si un candidato menciona el título (nombre de archivo) de
     OTRA fuente permitida y es corto (<= 80 palabras fuera del YAML), se
     trae el mejor fragmento de la fuente referida para esta consulta y se
     coloca inmediatamente antes del fragmento que remite a ella; el
     fragmento puente queda detrás de su destino.

Uso: python3 prototipo_alternativas.py --compartidos documento_completo --rerank sin --variantes base,R,TYR
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests" / "integration"))
sys.path.insert(0, str(RAIZ / "tests" / "unit" / "application"))
sys.path.insert(0, str(RAIZ / "docs proyecto" / "Ronda102_Diagnostico_Simulador"))

_PALABRA = re.compile(r"\w+", re.UNICODE)


def _sin_yaml(texto: str) -> str:
    from domain.conversational.section_affinity import _sin_encabezado_yaml
    return "\n".join(_sin_encabezado_yaml(texto.split("\n")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compartidos", choices=["documento_completo", "por_encabezado"], default="documento_completo")
    ap.add_argument("--rerank", choices=["con", "sin"], default="sin")
    ap.add_argument("--variantes", default="base,T,Y,R,TYR")
    ap.add_argument("--casos", default="")
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()

    import evaluacion_simulador as ev
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

    fixture = getattr(base.corpus, "__wrapped__", base.corpus)
    simuladores, titulo_de = fixture()
    sim = simuladores[a.rerank]
    rag, P = sim._rag, base.P
    fuentes = sim._sources.list_for_project(P)
    variables = sim._variables.list_for_project(P)
    intents = sim._intents.list_for_project(P)

    def titulo_afinidad(chunk, con_y: bool) -> str:
        if con_y and not chunk.section_title and not _PALABRA.findall(_sin_yaml(chunk.text or "")):
            return ""
        return affinity_title(chunk.section_title, chunk.text, titulo_de[chunk.source_id])

    def referencias(chunk, permitidas):
        texto = (chunk.text or "").lower()
        refs = []
        for s in fuentes:
            if s.id == chunk.source_id or s.id not in permitidas:
                continue
            nombre = s.title.lower()
            raiz = re.sub(r"\.[a-z0-9]{1,5}$", "", nombre)
            if nombre in texto or (len(raiz) >= 6 and raiz in texto):
                refs.append(s.id)
        return refs

    def es_corto(chunk) -> bool:
        return len(_PALABRA.findall(_sin_yaml(chunk.text or ""))) <= 80

    def ejecutar(consulta: str, variante: str):
        trace = sim.execute(P, consulta, {}, limit=5)
        if trace.action.value != "responder" or not trace.applied_metadata_filters:
            return trace.search_results, trace
        permitidas = {s.id for s in fuentes if sim._source_matches_filters(P, s.id, variables,
                                                                           trace.applied_metadata_filters)}
        texto = trace.retrieval_query or consulta
        if "T" in variante and trace.retrieval_query:
            from domain.conversational.section_affinity import raices
            if len(raices(trace.retrieval_query)) < 3:
                texto = consulta
        pool = rag.search_hybrid(P, texto, limit=20, only_usable_sources=True, rerank=rag.has_reranker,
                                 source_ids=permitidas)
        if "R" in variante:
            nuevo, vistos = [], set()
            for r in pool:
                refs = referencias(r.chunk, permitidas) if es_corto(r.chunk) else []
                for sid in refs:
                    mejores = rag.search_hybrid(P, texto, limit=3, only_usable_sources=True,
                                                rerank=rag.has_reranker, source_ids={sid})
                    # el mejor fragmento CON contenido (no solo encabezado YAML)
                    mejor = next((m for m in mejores if _PALABRA.findall(_sin_yaml(m.chunk.text or ""))), None)
                    if mejor is not None and mejor.chunk.id not in vistos:
                        nuevo.append(mejor)
                        vistos.add(mejor.chunk.id)
                if r.chunk.id not in vistos:
                    nuevo.append(r)
                    vistos.add(r.chunk.id)
            pool = nuevo[:20]
        intent = next(i for i in intents if i.name == trace.matched_intent_name)
        afinidad = SectionAffinity(intent, intents, consulta, sim._catalog_mention_masker(P))
        def puntaje(chunk) -> float:
            propio = afinidad.score(titulo_afinidad(chunk, "Y" in variante))
            if "P" not in variante:
                return propio
            # P: la sección hereda la afinidad de sus encabezados superiores
            # (ruta guardada por por_encabezado, Ronda 100).
            ancestros = [h.title for h in (chunk.section_path or [])[:-1]]
            return max([propio, *(afinidad.score(t) for t in ancestros)])

        puntajes = [puntaje(r.chunk) for r in pool]
        orden = combine_with_retrieval(puntajes)[:5]
        return [pool[i] for i in orden], trace

    elegidos = set(filter(None, a.casos.split(",")))
    resultados: dict = {}
    for variante in a.variantes.split(","):
        posiciones = []
        for cid, _grupo, consulta, fuente, texto in ev.CASOS:
            if elegidos and cid not in elegidos:
                continue
            final, _ = ejecutar(consulta, variante)
            pos = next((i for i, r in enumerate(final, 1)
                        if titulo_de[r.chunk.source_id] == fuente and texto in r.chunk.text), None)
            posiciones.append(pos)
            if a.casos and len(elegidos) == 1:
                for i, r in enumerate(final, 1):
                    print(f"     {variante} {i}. {titulo_de[r.chunk.source_id]} «{(r.chunk.section_title or '')[:40]}» "
                          f"{(r.chunk.text or '')[:60]!r}")
            resultados.setdefault(variante, {})[cid] = pos
        n = len(posiciones)
        r1 = sum(1 for p in posiciones if p == 1) / n
        mrr = sum(1 / p for p in posiciones if p) / n
        print(f"{a.compartidos:18} {a.rerank}-rerank {variante:5} R@1 {r1:.2f} MRR {mrr:.3f}  "
              + " ".join(f"{c}={p}" for c, p in resultados[variante].items()))
    if a.salida:
        previo = json.loads(a.salida.read_text()) if a.salida.exists() else {}
        previo.setdefault(f"{a.compartidos}|{a.rerank}", {}).update(resultados)
        a.salida.write_text(json.dumps(previo, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
