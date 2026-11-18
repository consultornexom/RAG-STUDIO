"""Ronda 105b (P1) -- condición 6 de NEXOM: ejecutar el motor de Calidad
(RunEvaluation, el mismo de la pestaña Calidad) sobre un banco de 14 casos
con los cinco archivos reales de LOTE01, con el código anterior y con el
nuevo, y comparar veredictos, acción, intención, puesto de la fuente
esperada y Recall@3.

Dos configuraciones de motor:
  escritorio  RagService CON modelo de reranking (como la app de escritorio)
  runtime     RagService SIN modelo de reranking (como el Runtime de RAG Studio)
Ajuste del proyecto: Automático (predeterminado, el de todos los proyectos).

Todo en memoria; no escribe en ningún proyecto ni índice. Intenciones y
metadatos: los supuestos de tests/integration/test_ronda102_lote01_simulador.py.

Uso:
  python3 calidad_lote01.py --codigo <raíz> --config escritorio|runtime --salida c.json
  python3 calidad_lote01.py --comparar antes.json despues.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_DOCS = AQUI.parents[1]


def _titulos(texto: str, titulo_de: dict) -> str:
    for sid, titulo in titulo_de.items():
        texto = texto.replace(sid, titulo)
    return texto


def comparar(a: Path, b: Path) -> int:
    x, y = json.loads(a.read_text()), json.loads(b.read_text())
    difs = [k for k in sorted(set(x["casos"]) | set(y["casos"])) if x["casos"].get(k) != y["casos"].get(k)]
    for k in difs:
        print(f"DIFERENCIA {k}:\n  antes:   {x['casos'].get(k)}\n  después: {y['casos'].get(k)}")
    print(f"Recall@3 antes {x['recall_at_3']} / después {y['recall_at_3']}; "
          f"veredicto global antes {x['veredicto_global']} / después {y['veredicto_global']}")
    print(f"{len(x['casos'])} casos; diferencias: {difs or 'ninguna'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", type=Path)
    ap.add_argument("--config", choices=["escritorio", "runtime"])
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--comparar", nargs=2, type=Path)
    a = ap.parse_args()
    if a.comparar:
        return comparar(*a.comparar)
    raiz = a.codigo.resolve()
    for p in (RAIZ_DOCS / "docs proyecto" / "Ronda102_Diagnostico_Simulador", RAIZ_DOCS / "tests" / "integration",
              raiz / "tests" / "unit" / "application", raiz):
        sys.path.insert(0, str(p))
    import evaluacion_simulador as ev
    import test_ronda102_lote01_simulador as base
    from fakes_quality import InMemoryEvaluationRunRepository, InMemoryTestCaseRepository

    from application.conversational.service import ConversationalService
    from application.quality.commands.run_evaluation import RunEvaluation
    from domain.conversational.entities import RuleActionType
    from domain.quality.entities import TestCase, TestCategory

    simuladores, titulo_de = getattr(base.corpus, "__wrapped__", base.corpus)()
    sim = simuladores["con" if a.config == "escritorio" else "sin"]
    servicio = ConversationalService(
        sim._intents, sim._variables, sim._guardrails, sim._channeling, sim._source_metadata, sim._rag,
        source_repository=sim._sources, schema_repository=sim._schemas, catalog_repository=sim._catalogs,
    )
    id_de = {titulo: sid for sid, titulo in titulo_de.items()}
    casos_repo, runs = InMemoryTestCaseRepository(), InMemoryEvaluationRunRepository()
    for cid, _g, consulta, fuente, _t in ev.CASOS:
        casos_repo.save(TestCase(
            project_id=base.P, code=cid, category=TestCategory.RESPUESTA_DIRECTA, query_text=consulta,
            expected_action=RuleActionType.RESPONDER, expected_source_id=id_de[fuente],
        ))
    run = RunEvaluation(casos_repo, runs, servicio).execute(base.P)
    datos = {
        "codigo": str(a.codigo), "config": a.config,
        "veredicto_global": run.overall_verdict.value, "recall_at_3": run.recall_at_k(3),
        "casos": {
            item.test_case_code: {
                "veredicto": item.verdict.value,
                "accion": item.actual_action.value if item.actual_action else None,
                "intencion": item.actual_intent, "rango_fuente_esperada": item.expected_source_rank,
                # ids de fuente -> título (los ids cambian en cada construcción en memoria)
                "discrepancias": [_titulos(m, titulo_de) for m in item.mismatches], "error": item.error,
            }
            for item in sorted(run.items, key=lambda i: i.test_case_code)
        },
    }
    print(json.dumps({k: v for k, v in datos.items() if k != "casos"}, ensure_ascii=False))
    if a.salida:
        a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
