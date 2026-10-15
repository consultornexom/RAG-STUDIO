"""RAG-INC-01d · Fase 1 — saneamiento controlado de intenciones con nombre
duplicado (corpus B), SOLO sobre una copia descartable.

Regla autorizada por NEXOM:
- se agrupan las intenciones por `name`;
- un grupo solo se sanea si todas sus filas son **duplicados exactos**: todos
  los campos iguales salvo `id`, `created_at` y `updated_at`;
- se conserva la de `created_at` más antiguo (desempate por `id`) y se
  eliminan las redundantes;
- si un grupo NO es exacto, no se toca nada y se reporta para decisión de
  NEXOM (nunca se renombra automáticamente).

Las demás tablas referencian intenciones por NOMBRE (`test_case.expected_intent`,
`evaluation_result_item.actual_intent`), así que conservar una fila por
nombre no rompe ninguna referencia. También se verifica que ninguna tabla
referencie por id a una intención eliminada.

Uso (copia ya migrada a 0021):
  python3 sanear_intenciones_duplicadas.py --db <copia>/project.db --informe <salida.json> [--aplicar]
Sin --aplicar solo analiza (sin escribir).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_IGNORADOS = ("id", "created_at", "updated_at")


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def analizar(con: sqlite3.Connection) -> dict:
    con.row_factory = sqlite3.Row
    columnas = [r[1] for r in con.execute("PRAGMA table_info(intent)")]
    filas = [dict(r) for r in con.execute("SELECT * FROM intent ORDER BY name, created_at, id")]
    grupos: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        grupos[f["name"]].append(f)
    resultado = {"intenciones": len(filas), "grupos_duplicados": []}
    for nombre, miembros in grupos.items():
        if len(miembros) < 2:
            continue
        comparables = [{c: m[c] for c in columnas if c not in _IGNORADOS} for m in miembros]
        diferencias = sorted({c for comp in comparables[1:] for c in comp if comp[c] != comparables[0][c]})
        conservar = miembros[0]
        resultado["grupos_duplicados"].append({
            "name": nombre,
            "exacto": not diferencias,
            "campos_distintos": diferencias,
            "filas": [{"id": m["id"], "created_at": m["created_at"], "updated_at": m["updated_at"],
                       "priority": m["priority"], "active": m["active"], "risk_level": m["risk_level"],
                       "positive_examples": json.loads(m["positive_examples"] or "[]"),
                       "negative_examples": json.loads(m["negative_examples"] or "[]"),
                       "required_variables": json.loads(m["required_variables"] or "[]"),
                       "optional_variables": json.loads(m["optional_variables"] or "[]"),
                       "fallback_channeling_code": m["fallback_channeling_code"],
                       "resolution_mode": m["resolution_mode"]} for m in miembros],
            "conservar_id": conservar["id"],
            "eliminar_ids": [m["id"] for m in miembros[1:]],
        })
    return resultado


def referencias_por_id(con: sqlite3.Connection, ids: list[str]) -> list[str]:
    """Columnas de cualquier tabla que contengan alguno de esos ids."""
    hallazgos = []
    for (tabla,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if tabla == "intent":
            continue
        for col in [r[1] for r in con.execute(f"PRAGMA table_info({tabla})")]:
            for i in ids:
                n = con.execute(f'SELECT COUNT(*) FROM "{tabla}" WHERE CAST("{col}" AS TEXT) LIKE ?', (f"%{i}%",)).fetchone()[0]
                if n:
                    hallazgos.append(f"{tabla}.{col} contiene {i} ({n})")
    return hallazgos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--informe", required=True, type=Path)
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()

    antes = _sha(a.db)
    con = sqlite3.connect(a.db)
    try:
        analisis = analizar(con)
        no_exactos = [g["name"] for g in analisis["grupos_duplicados"] if not g["exacto"]]
        eliminar = [i for g in analisis["grupos_duplicados"] if g["exacto"] for i in g["eliminar_ids"]]
        refs = referencias_por_id(con, eliminar)
        informe = {"db": str(a.db), "sha256_antes": antes, **analisis, "grupos_no_exactos": no_exactos,
                   "referencias_por_id_a_eliminadas": refs, "aplicado": False}
        if a.aplicar and not no_exactos and not refs and eliminar:
            with con:
                con.executemany("DELETE FROM intent WHERE id = ?", [(i,) for i in eliminar])
            informe["aplicado"] = True
            informe["eliminadas"] = eliminar
        informe["intenciones_despues"] = con.execute("SELECT COUNT(*) FROM intent").fetchone()[0]
        informe["nombres_duplicados_despues"] = [r[0] for r in con.execute(
            "SELECT name FROM intent GROUP BY name HAVING COUNT(*) > 1")]
        informe["integrity_check"] = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    informe["sha256_despues"] = _sha(a.db)
    a.informe.parent.mkdir(parents=True, exist_ok=True)
    a.informe.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("intenciones", "intenciones_despues", "grupos_no_exactos",
                                               "referencias_por_id_a_eliminadas", "aplicado",
                                               "nombres_duplicados_despues")}, ensure_ascii=False))
    if no_exactos:
        print("DETENIDO: hay grupos no exactos; se requiere decisión de NEXOM.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
