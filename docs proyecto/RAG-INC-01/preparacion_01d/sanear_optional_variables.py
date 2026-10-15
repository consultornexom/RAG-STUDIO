"""RAG-INC-01d · Fase 1 — saneamiento controlado del corpus D (autorización
NEXOM: DATA_DEFECT). SOLO se aplica sobre una COPIA de la instalación.

Cambio único autorizado: en la intención indicada, `optional_variables` pasa
de exactamente el valor esperado (p. ej. ["modalidad", "nivel_academico"],
referencias huérfanas: no existen como variables conversacionales) a `[]`.

Comprobaciones (cualquier discrepancia aborta sin escribir):
- la base es una copia: nunca la ruta de la instalación original;
- existe exactamente una intención con ese nombre en el proyecto;
- su `optional_variables` actual es EXACTAMENTE el esperado;
- los códigos que se quitan no existen en `conversational_variable` (siguen
  siendo huérfanos);
- después: solo cambió `optional_variables` de esa fila (el resto de columnas
  de todas las intenciones y la tabla de variables quedan idénticos) e
  `integrity_check` = ok.

No crea variables ni convierte campos de metadatos en variables. No toca
`updated_at`: no es una edición de diseño, es saneamiento de datos para
exportar.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class SaneamientoError(RuntimeError):
    pass


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _filas(con: sqlite3.Connection, sql: str, *args) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql, args)]


def vaciar_optional_variables(db: Path, original: Path, project_id: str, intent_name: str, esperado: list[str]) -> dict:
    db = db.resolve()
    if original.resolve() in db.parents:
        raise SaneamientoError(f"Se negó a modificar la instalación original: {db}")
    registro: dict = {"project_id": project_id, "intent_name": intent_name, "db": str(db),
                      "sha256_antes": _sha(db)}
    con = sqlite3.connect(db)
    try:
        intents_antes = _filas(con, "SELECT * FROM intent WHERE project_id = ? ORDER BY id", project_id)
        variables_antes = _filas(con, "SELECT * FROM conversational_variable WHERE project_id = ? ORDER BY id", project_id)
        objetivo = [i for i in intents_antes if i["name"] == intent_name]
        if len(objetivo) != 1:
            raise SaneamientoError(f"Se esperaba exactamente 1 intención {intent_name!r}; hay {len(objetivo)}.")
        intent = objetivo[0]
        actual = json.loads(intent["optional_variables"] or "[]")
        registro.update({"intent_id": intent["id"], "optional_variables_antes": actual})
        if actual != esperado:
            raise SaneamientoError(f"optional_variables actual {actual!r} no es el esperado {esperado!r}.")
        codigos = {v["code"] for v in variables_antes}
        no_huerfanos = [c for c in actual if c in codigos]
        if no_huerfanos:
            raise SaneamientoError(f"{no_huerfanos!r} SÍ existen como variables: no son huérfanos.")
        with con:
            n = con.execute("UPDATE intent SET optional_variables = '[]' WHERE id = ? AND project_id = ?",
                            (intent["id"], project_id)).rowcount
            if n != 1:
                raise SaneamientoError(f"UPDATE afectó {n} filas.")
            # Verificación dentro de la transacción: solo cambió esa columna de esa fila.
            intents_despues = _filas(con, "SELECT * FROM intent WHERE project_id = ? ORDER BY id", project_id)
            esperado_despues = [dict(i, optional_variables="[]") if i["id"] == intent["id"] else i for i in intents_antes]
            if intents_despues != esperado_despues:
                raise SaneamientoError("Cambió algo más que optional_variables de la intención indicada.")
            if _filas(con, "SELECT * FROM conversational_variable WHERE project_id = ? ORDER BY id", project_id) != variables_antes:
                raise SaneamientoError("La tabla conversational_variable cambió.")
        registro["optional_variables_despues"] = json.loads(
            con.execute("SELECT optional_variables FROM intent WHERE id = ?", (intent["id"],)).fetchone()[0])
        registro["integrity_check"] = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    registro["sha256_despues"] = _sha(db)
    if registro["integrity_check"] != "ok":
        raise SaneamientoError(f"integrity_check = {registro['integrity_check']}")
    return registro
