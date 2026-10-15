"""RAG-INC-01d · Fase 1 — corpus D (AGENTE UDL, instalación real de macOS).

Se ejecuta en el equipo de NEXOM, con RAG Studio CERRADO. Nunca abre la
instalación original con la aplicación (eso la migraría) y nunca escribe en
ella. Tampoco toca instantáneas históricas.

Parte 1, solo lectura sobre el original. Todo se lee de copias temporales:
  - project.db vivo: revisión Alembic, proyecto, `knowledge_base_id` si
    existe, fuentes sin huella e instantáneas registradas;
  - instantánea más reciente registrada (v5): carpeta física,
    `snapshot_identity.json` (proyecto y versión), legibilidad e integridad de
    su project.db, presencia de 0021, y compuertas 01b/01c (se intenta
    exportarla directamente; el exportador solo lee una copia temporal).
Parte 2, copia de trabajo: se copia la instalación completa a <out>/instalacion;
  si se indica --vaciar-optional-variables-de, se aplica a la COPIA (todavía en
  0020) el saneamiento autorizado (sanear_optional_variables.py) con registro
  antes/después; luego, con la aplicación sobre la copia (que migra solo la copia a 0021), se
  verifican las huellas, se publica una instantánea nueva y se genera el
  paquete candidato con la compuerta 01c (generar_candidato_nkp.py).
Parte 3: se comprueba que el original no cambió (hashes del project.db vivo y
  de su -wal, y huella de la carpeta de la instantánea v5).

Uso:
  python3 preparar_candidato_D.py --instalacion-original <ruta>/data_AGENTE_UDL \
      --project-id 6073eda1-268d-48bd-8257-e6d3fef4f981 --tenant <tenant> --out <carpeta_nueva>
Resultado: <out>/informe_D.json y <out>/candidato/ (si la Parte 2 pasa).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain.knowledge_package.entities import SnapshotDescriptor  # noqa: E402
from infrastructure.exporters.nexom_knowledge_package import NexomKnowledgePackageExporter  # noqa: E402
from infrastructure.filesystem.snapshot_identity import content_fingerprint  # noqa: E402


def sha256(ruta: Path) -> str | None:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else None


def copia_legible(db: Path, destino: Path) -> sqlite3.Connection:
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, destino / "project.db")
    if Path(str(db) + "-wal").is_file():
        shutil.copy2(Path(str(db) + "-wal"), destino / "project.db-wal")
    con = sqlite3.connect(destino / "project.db")
    con.row_factory = sqlite3.Row
    return con


def columnas(con: sqlite3.Connection, tabla: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}


def parte1(original: Path, pid: str, tmp: Path, out: Path) -> dict:
    db_vivo = original / "projects" / pid / "project.db"
    con = copia_legible(db_vivo, tmp / "vivo")
    try:
        r: dict = {"project_db_vivo": str(db_vivo),
                   "alembic_vivo": con.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                   "integrity_check_vivo": con.execute("PRAGMA integrity_check").fetchone()[0]}
        tiene_kb = "knowledge_base_id" in columnas(con, "project")
        r["vivo_con_0021"] = tiene_kb and "lineage_id" in columnas(con, "source")
        r["knowledge_base_id_vivo"] = con.execute("SELECT knowledge_base_id FROM project").fetchone()[0] if tiene_kb else None
        r["fuentes"] = con.execute("SELECT COUNT(*) FROM source WHERE project_id = ?", (pid,)).fetchone()[0]
        r["fuentes_sin_huella"] = con.execute(
            "SELECT COUNT(*) FROM source WHERE project_id = ? AND (content_hash IS NULL OR content_hash = '') "
            "AND source_type NOT IN ('api','base_de_datos')", (pid,)).fetchone()[0]
        r["chunks"] = con.execute("SELECT COUNT(*) FROM chunk WHERE project_id = ?", (pid,)).fetchone()[0]
        snaps = [dict(s) for s in con.execute(
            "SELECT id, version, snapshot_dir, created_at FROM project_snapshot WHERE project_id = ? ORDER BY version", (pid,))]
    finally:
        con.close()
    r["instantaneas_registradas"] = [{**s, "carpeta_existe": Path(s["snapshot_dir"]).is_dir()} for s in snaps]
    if not snaps:
        r["ultima"] = None
        return r
    ultima = snaps[-1]
    carpeta = Path(ultima["snapshot_dir"])
    u: dict = {"version": ultima["version"], "snapshot_id": ultima["id"], "snapshot_dir": str(carpeta),
               "carpeta_existe": carpeta.is_dir()}
    if carpeta.is_dir():
        ident = carpeta / "snapshot_identity.json"
        if ident.is_file():
            datos = json.loads(ident.read_text(encoding="utf-8"))
            u["snapshot_identity"] = {"existe": True, "project_id": datos.get("project_id"),
                                      "snapshot_version": datos.get("snapshot_version"),
                                      "corresponde": datos.get("project_id") == pid and datos.get("snapshot_version") == ultima["version"]}
        else:
            u["snapshot_identity"] = {"existe": False}
        db_snap = carpeta / "project.db"
        u["project_db_existe"] = db_snap.is_file()
        if db_snap.is_file():
            cs = copia_legible(db_snap, tmp / "snap")
            try:
                u["alembic"] = cs.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                u["integrity_check"] = cs.execute("PRAGMA integrity_check").fetchone()[0]
                u["con_0021"] = "knowledge_base_id" in columnas(cs, "project") and "lineage_id" in columnas(cs, "source")
            finally:
                cs.close()
        u["huella_antes"] = content_fingerprint(carpeta)
        # Compuertas 01b/01c directamente sobre la instantánea (solo lee una copia temporal).
        descriptor = SnapshotDescriptor(id=ultima["id"], project_id=pid, version=ultima["version"],
                                        snapshot_dir=str(carpeta), created_at=datetime.fromisoformat(
                                            str(ultima["created_at"]).replace(" ", "T")).replace(tzinfo=timezone.utc))
        try:
            res = NexomKnowledgePackageExporter().export(descriptor, "verificacion-01d", str(out / "intento_ultima_instantanea"))
            u["compuertas"] = {"resultado": "PASS", "package_id": res.package_id,
                               "conformidad": res.conformance.summary() if res.conformance else None}
        except Exception as exc:  # noqa: BLE001 - se informa la compuerta que bloqueó
            u["compuertas"] = {"resultado": "BLOQUEADA", "error": type(exc).__name__, "detalle": str(exc)[:1000]}
    r["ultima"] = u
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instalacion-original", required=True, type=Path)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--out", required=True, type=Path)
    # Saneamiento autorizado por NEXOM (DATA_DEFECT), solo sobre la copia:
    ap.add_argument("--vaciar-optional-variables-de", metavar="INTENCION",
                    help="nombre de la intención cuyo optional_variables se vacía en la COPIA")
    ap.add_argument("--optional-variables-esperadas", default="[]",
                    help='valor JSON exacto que debe tener antes, p. ej. \'["modalidad", "nivel_academico"]\'')
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"--out debe ser una carpeta nueva: {a.out}")
    a.out.mkdir(parents=True)
    original = a.instalacion_original.resolve()
    db_vivo = original / "projects" / a.project_id / "project.db"
    if not db_vivo.is_file():
        raise SystemExit(f"No existe {db_vivo}")
    hashes_antes = {"project_db": sha256(db_vivo), "project_db_wal": sha256(Path(str(db_vivo) + "-wal"))}

    informe: dict = {"corpus": "D", "project_id": a.project_id, "instalacion_original": str(original),
                     "ejecutado": datetime.now(timezone.utc).isoformat()}
    with tempfile.TemporaryDirectory() as tmp:
        informe["parte1_original"] = parte1(original, a.project_id, Path(tmp), a.out)

    # Parte 2: copia de trabajo de la instalación completa.
    copia = a.out / "instalacion"
    shutil.copytree(original, copia, ignore=shutil.ignore_patterns("*.lock"))
    if a.vaciar_optional_variables_de:
        from sanear_optional_variables import vaciar_optional_variables

        informe["saneamiento_copia"] = vaciar_optional_variables(
            copia / "projects" / a.project_id / "project.db", original, a.project_id,
            a.vaciar_optional_variables_de, json.loads(a.optional_variables_esperadas),
        )
    candidato = a.out / "candidato"
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name("generar_candidato_nkp.py")), "--corpus", "D",
                           "--instalacion", str(copia), "--project-id", a.project_id, "--tenant", a.tenant,
                           "--out", str(candidato)], capture_output=True, text=True)
    informe["parte2_copia"] = {"returncode": proc.returncode, "salida_final": proc.stdout.strip().splitlines()[-1:] if proc.stdout else [],
                               "stderr_final": proc.stderr.strip().splitlines()[-5:]}
    if (candidato / "informe_candidato.json").is_file():
        informe["parte2_copia"]["informe_candidato"] = json.loads((candidato / "informe_candidato.json").read_text())

    # Parte 3: el original no cambió.
    hashes_despues = {"project_db": sha256(db_vivo), "project_db_wal": sha256(Path(str(db_vivo) + "-wal"))}
    ultima = informe["parte1_original"].get("ultima") or {}
    huella_despues = content_fingerprint(Path(ultima["snapshot_dir"])) if ultima.get("carpeta_existe") else None
    informe["parte3_original_intacto"] = {
        "project_db_vivo": hashes_antes == hashes_despues, "hashes": hashes_antes,
        "ultima_instantanea": (huella_despues == ultima.get("huella_antes")) if huella_despues else None,
    }
    (a.out / "informe_D.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    p1 = informe["parte1_original"]
    if "saneamiento_copia" in informe:
        print("saneamiento_copia:", json.dumps(informe["saneamiento_copia"], ensure_ascii=False))
    print(json.dumps({"alembic_vivo": p1["alembic_vivo"], "fuentes": p1["fuentes"], "sin_huella": p1["fuentes_sin_huella"],
                      "ultima": {k: ultima.get(k) for k in ("version", "carpeta_existe", "con_0021", "snapshot_identity", "compuertas")},
                      "candidato_returncode": proc.returncode, "original_intacto": informe["parte3_original_intacto"]},
                     ensure_ascii=False, indent=1, default=str))
    ok = proc.returncode == 0 and all(v for k, v in informe["parte3_original_intacto"].items() if k != "hashes" and v is not None)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # pragma: no cover - diagnóstico legible en el equipo de NEXOM
        traceback.print_exc()
        raise SystemExit(1) from None
