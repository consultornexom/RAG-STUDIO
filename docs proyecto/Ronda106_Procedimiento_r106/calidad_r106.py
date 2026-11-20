"""Ronda 106 -- casos de Calidad con el motor de Calidad real (RunEvaluation,
el de la pestaña Calidad) con el procedimiento r105b y con r106.

Dos modos:

  --lote01
      Banco de 14 casos LOTE01 (fuente esperada y acción RESPONDER) sobre los
      cinco archivos reales con la configuración real de AGENTE UDL y la
      intención real de requisitos (tests/integration/
      test_ronda106_procedimiento_r106.py). Todo en memoria.

  --agentproj <archivo.agentproj> [--modelos data/models]
      Para NEXOM: importa una COPIA del .agentproj en una instalación temporal
      (política "fork"; el archivo original no se modifica: se verifica su
      SHA-256 antes y después), ejecuta la evaluación completa del banco del
      proyecto con r105b y luego con r106 (cambiando solo el ajuste de la
      copia) y compara caso por caso: veredicto, acción, intención y puesto
      de la fuente esperada; Recall@3 y MRR.

Uso:
  python3 calidad_r106.py --lote01 [--salida c.json]
  python3 calidad_r106.py --agentproj AGENTE_UDL.agentproj --modelos <carpeta de modelos> [--salida c.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))


def _resumen(run, nombre_de=lambda item: item.test_case_code) -> dict:
    return {
        "veredicto_global": run.overall_verdict.value,
        "recall_at_3": run.recall_at_k(3),
        "mrr": round(run.mean_reciprocal_rank(), 3) if run.mean_reciprocal_rank() is not None else None,
        "casos": {
            nombre_de(item): {
                "veredicto": item.verdict.value,
                "accion": item.actual_action.value if item.actual_action else None,
                "intencion": item.actual_intent,
                "rango_fuente_esperada": item.expected_source_rank,
                "error": item.error,
            }
            for item in sorted(run.items, key=lambda i: i.test_case_code or i.test_case_id)
        },
    }


def _comparar(a: dict, b: dict) -> dict:
    """Casos que empeoran en b respecto de a (veredicto o puesto)."""
    orden = {"verde": 0, "amarillo": 1, "rojo": 2}
    peores, cambios = [], []
    for clave in sorted(set(a["casos"]) | set(b["casos"])):
        x, y = a["casos"].get(clave), b["casos"].get(clave)
        if x == y:
            continue
        cambios.append(clave)
        if x and y and (orden.get(y["veredicto"], 3) > orden.get(x["veredicto"], 3)
                        or (y["rango_fuente_esperada"] or 99) > (x["rango_fuente_esperada"] or 99)):
            peores.append(clave)
        if x and y and (x["accion"], x["intencion"]) != (y["accion"], y["intencion"]):
            peores.append(clave + " (decisión distinta)")
    return {"cambios": cambios, "peores": peores}


def lote01() -> dict:
    sys.path.insert(0, str(RAIZ / "tests" / "integration"))
    sys.path.insert(0, str(RAIZ / "tests" / "unit" / "application"))
    import test_ronda106_procedimiento_r106 as t
    from fakes_quality import InMemoryEvaluationRunRepository, InMemoryTestCaseRepository

    from application.conversational.service import ConversationalService
    from application.quality.commands.run_evaluation import RunEvaluation
    from domain.conversational.entities import RuleActionType
    from domain.quality.entities import TestCase, TestCategory

    simuladores, titulo_de = t.construir("documento_completo")
    id_de = {titulo: sid for sid, titulo in titulo_de.items()}
    salida = {}
    for procedimiento, sim in simuladores.items():
        servicio = ConversationalService(
            sim._intents, sim._variables, sim._guardrails, sim._channeling, sim._source_metadata, sim._rag,
            source_repository=sim._sources, schema_repository=sim._schemas, catalog_repository=sim._catalogs,
            retrieval_procedure=lambda _pid, p=procedimiento: p,
        )
        casos, runs = InMemoryTestCaseRepository(), InMemoryEvaluationRunRepository()
        for cid, consulta, fuente, _texto in t.CASOS:
            casos.save(TestCase(project_id=t.P, code=cid, category=TestCategory.RESPUESTA_DIRECTA, query_text=consulta,
                                expected_action=RuleActionType.RESPONDER, expected_source_id=id_de[fuente]))
        salida[procedimiento] = _resumen(RunEvaluation(casos, runs, servicio).execute(t.P))
    return salida


def agentproj(archivo: Path, modelos: Path) -> dict:
    from app.bootstrap import bootstrap

    huella = hashlib.sha256(archivo.read_bytes()).hexdigest()
    salida: dict = {"agentproj": archivo.name, "sha256": huella}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "instalacion"
        base.mkdir()
        (base / "models").symlink_to(modelos.resolve(), target_is_directory=True)
        copia = Path(tmp) / archivo.name
        shutil.copy2(archivo, copia)
        ctx = bootstrap(base_dir=base, log_level="WARNING")
        proyecto = ctx.project_service.import_project(str(copia), identity_policy="fork")
        salida["procedimiento_del_paquete"] = ctx.project_service.get_retrieval_procedure(proyecto.id)[0]
        consultas = {c.id: c for c in ctx.quality_service.list_test_cases(proyecto.id)}

        def nombre(item):
            caso = consultas.get(item.test_case_id)
            return f"{item.test_case_code}|{caso.query_text if caso else item.test_case_id}"

        for procedimiento in ("r105b", "r106"):
            ctx.project_service.update_retrieval_procedure(proyecto.id, procedimiento)
            salida[procedimiento] = _resumen(ctx.quality_service.run_evaluation(proyecto.id, scope="completa"), nombre)
    salida["original_intacto"] = hashlib.sha256(archivo.read_bytes()).hexdigest() == huella
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote01", action="store_true")
    ap.add_argument("--agentproj", type=Path)
    ap.add_argument("--modelos", type=Path, default=RAIZ / "data" / "models")
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()
    datos = lote01() if a.lote01 else agentproj(a.agentproj, a.modelos)
    datos["comparacion_r106_vs_r105b"] = _comparar(datos["r105b"], datos["r106"])
    for procedimiento in ("r105b", "r106"):
        r = datos[procedimiento]
        print(f"{procedimiento}: veredicto {r['veredicto_global']}, Recall@3 {r['recall_at_3']}, MRR {r['mrr']}; "
              + ", ".join(f"{k.split('|')[0]}={v['rango_fuente_esperada']}" for k, v in r["casos"].items()))
    print("cambios:", datos["comparacion_r106_vs_r105b"]["cambios"] or "ninguno")
    print("peores en r106:", datos["comparacion_r106_vs_r105b"]["peores"] or "ninguno")
    if a.salida:
        a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
