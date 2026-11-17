"""Ronda 104 -- DIAGNÓSTICO (sin cambios de código): «¿Qué documentos
necesito para entrar al bachillerato?» -- los fragmentos "puente" de los
planes («Información compartida aplicable a este plantel», que solo remiten
a requisitos_ingreso.md) ganan al fragmento con los requisitos reales.

Corpus: los cinco documentos reales de LOTE01 (tests/fixtures/
lote01_bachillerato), modelos reales (data/models, sin red), motor real
(SimulateConversation = POST /messages). Intenciones y metadatos: los de
tests/integration/test_ronda102_lote01_simulador.py (supuestos; no se
tiene el project.db de la instantánea v2).

Para cada variante de fragmentación de los documentos compartidos
(documento_completo | por_encabezado 500/60/80) y con/sin reranking,
muestra, para el fragmento de requisitos reales y los dos puentes:
  - texto de búsqueda que usa el Simulador;
  - puesto en la lista semántica, en la textual (BM25) y en la fusión;
  - puntaje del reranker;
  - puesto en el pool de 20 y en el top 5 final (tras la afinidad).

Uso (raíz del repositorio):
    python3 "docs proyecto/Ronda104_Fragmentos_Puente/diagnostico_puentes.py" --compartidos documento_completo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests" / "integration"))
sys.path.insert(0, str(RAIZ / "tests" / "unit" / "application"))

CONSULTAS = [
    "¿Qué documentos necesito para entrar al bachillerato?",
    "¿Cuáles son los requisitos para ingresar al Bachillerato de la Universidad de León?",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compartidos", choices=["documento_completo", "por_encabezado"], default="documento_completo")
    ap.add_argument("--rerank", choices=["con", "sin", "ambos"], default="ambos")
    a = ap.parse_args()

    import test_ronda102_lote01_simulador as base
    from domain.ingestion.entities import FragmentationStrategy

    if a.compartidos == "por_encabezado":
        # Misma política que los planes para los documentos compartidos.
        original = base.IngestionService.set_fragmentation_policy

        def politica(self, project_id, tipo, **kw):
            if tipo in ("informacion_admisiones", "informacion_academica"):
                kw = dict(strategy=FragmentationStrategy.POR_ENCABEZADO, target_tokens=500, overlap_tokens=60,
                          min_tokens=80)
            return original(self, project_id, tipo, **kw)

        base.IngestionService.set_fragmentation_policy = politica

    fixture = getattr(base.corpus, "__wrapped__", base.corpus)
    simuladores, titulo_de = fixture()
    print(f"== documentos compartidos: {a.compartidos}")
    ejemplo = simuladores["sin"]
    chunks = [c for s in titulo_de for c in ejemplo._rag._chunk_repository.list_for_source(base.P, s)] \
        if hasattr(ejemplo._rag, "_chunk_repository") else []
    if chunks:
        print(f"   fragmentos indexados: {len(chunks)}")

    def es_requisitos(chunk):
        return titulo_de[chunk.source_id] == "requisitos_ingreso.md" and "Acta de nacimiento" in chunk.text

    def es_puente(chunk):
        return "Para evitar duplicación" in chunk.text and titulo_de[chunk.source_id].startswith("bachillerato_")

    def etiqueta(chunk):
        if es_requisitos(chunk):
            return "REQUISITOS"
        if es_puente(chunk):
            return "PUENTE-" + ("HM" if "hilario" in titulo_de[chunk.source_id] else "TL")
        return None

    def puestos(lista):
        out = {}
        for i, r in enumerate(lista, 1):
            e = etiqueta(r.chunk)
            if e and e not in out:
                out[e] = i
        return out

    variantes = ["con", "sin"] if a.rerank == "ambos" else [a.rerank]
    for consulta in CONSULTAS:
        for variante in variantes:
            sim = simuladores[variante]
            rag = sim._rag
            trace = sim.execute(base.P, consulta, {}, limit=5)
            texto = trace.retrieval_query or consulta
            hybrid = rag._hybrid_search
            sem = hybrid._semantic.execute(base.P, texto, limit=40, only_usable_sources=True)
            txt = hybrid._text.execute(base.P, texto, limit=40, only_usable_sources=True)
            pool = rag.search_hybrid(base.P, texto, limit=20, only_usable_sources=True, rerank=rag.has_reranker)
            lab = rag.search_hybrid(base.P, consulta, limit=20, rerank=rag.has_reranker)
            print(f"\n[{variante} reranking] {consulta}")
            print(f"   intención {trace.matched_intent_name} ({trace.confidence:.3f}); texto de búsqueda: {texto!r}")
            print(f"   Búsqueda RAG (consulta original): {puestos(lab)}")
            print(f"   semántica: {puestos(sem)}   textual (BM25): {puestos(txt)}   pool: {puestos(pool)}")
            if rag.has_reranker:
                candidatos = [r.chunk for r in pool]
                puntajes = rag._hybrid_search._reranker.score(texto, [c.text for c in candidatos])
                for c, p in zip(candidatos, puntajes, strict=True):
                    if etiqueta(c):
                        print(f"   reranker {etiqueta(c):11} {p:+.3f}")
            print(f"   FINAL top 5: {puestos(trace.search_results)}")
            for i, (r, o) in enumerate(zip(trace.search_results, trace.result_ordering, strict=False), 1):
                print(f"     {i}. {titulo_de[r.chunk.source_id]:32} búsqueda #{o.retrieval_rank:<2} "
                      f"afinidad {o.affinity:.2f} «{o.affinity_title[:45]}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
