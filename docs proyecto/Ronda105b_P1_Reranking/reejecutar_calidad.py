"""Ronda 105b (P1) -- condición 6 de NEXOM: volver a ejecutar los casos de
Calidad existentes con el código anterior y con el nuevo, y comparar.

Trabaja SIEMPRE sobre una instalación temporal nueva: importa una COPIA del
.agentproj indicado (política "fork"), ejecuta la evaluación completa del
banco de pruebas del proyecto con el código de --codigo y guarda, por caso,
el veredicto, la acción, la intención y las fuentes recuperadas en orden, más
las métricas agregadas. No toca el .agentproj original ni ninguna otra
instalación. Los modelos se leen de --modelos (enlace simbólico, sin copiar).

Uso:
  python3 reejecutar_calidad.py --codigo <raíz del código> --agentproj <archivo> --salida r.json
  python3 reejecutar_calidad.py --comparar antes.json despues.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


def comparar(a: Path, b: Path) -> int:
    x, y = json.loads(a.read_text()), json.loads(b.read_text())
    difs = []
    for clave in sorted(set(x["casos"]) | set(y["casos"])):
        if x["casos"].get(clave) != y["casos"].get(clave):
            difs.append(clave)
            print(f"DIFERENCIA {clave}:\n  antes:   {x['casos'].get(clave)}\n  después: {y['casos'].get(clave)}")
    print(f"métricas antes:   {x['metricas']}\nmétricas después: {y['metricas']}")
    print(f"{len(x['casos'])} casos; diferencias: {difs or 'ninguna'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codigo", type=Path)
    ap.add_argument("--agentproj", type=Path)
    ap.add_argument("--modelos", type=Path, default=Path("data/models"))
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--comparar", nargs=2, type=Path)
    a = ap.parse_args()
    if a.comparar:
        return comparar(*a.comparar)
    sys.path.insert(0, str(a.codigo.resolve()))
    from app.bootstrap import bootstrap

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "instalacion"
        base.mkdir()
        (base / "models").symlink_to(a.modelos.resolve(), target_is_directory=True)
        copia = Path(tmp) / a.agentproj.name
        shutil.copy2(a.agentproj, copia)
        ctx = bootstrap(base_dir=base, log_level="WARNING")
        proyecto = ctx.project_service.import_project(str(copia), identity_policy="fork")
        run = ctx.quality_service.run_evaluation(proyecto.id, scope="completa")
        casos = {}
        consultas = {c.id: c for c in ctx.quality_service.list_test_cases(proyecto.id)}
        for item in sorted(run.items, key=lambda i: (i.test_case_code or "", i.test_case_id)):
            caso = consultas.get(item.test_case_id)
            # Además del veredicto, el orden de fragmentos que el Simulador
            # entrega para la misma consulta (lo que cambia con P1).
            traza = ctx.conversational_service.simulate(
                proyecto.id, caso.query_text, provided_variables=dict(caso.provided_variables or {}), limit=5,
            ) if caso else None
            casos[f"{item.test_case_code}|{caso.query_text if caso else item.test_case_id}"] = {
                "veredicto": item.verdict.value,
                "accion": item.actual_action.value if item.actual_action else None,
                "intencion": item.actual_intent, "discrepancias": item.mismatches, "error": item.error,
                "rango_fuente_esperada": item.expected_source_rank,
                # por contenido: los ids pueden cambiar al importar con "fork"
                "simulador_fragmentos": [
                    hashlib.sha256(r.chunk.text.encode()).hexdigest()[:12] for r in traza.search_results
                ] if traza else None,
                "simulador_reranking_aplicado": getattr(traza, "reranking_applied", None) if traza else None,
            }
        datos = {
            "codigo": str(a.codigo), "agentproj": a.agentproj.name,
            "metricas": {"veredicto_global": run.overall_verdict.value, "recall_at_3": run.recall_at_k(3),
                         "casos": len(run.items)},
            "casos": casos,
        }
    print(json.dumps(datos, ensure_ascii=False, indent=1))
    if a.salida:
        a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
