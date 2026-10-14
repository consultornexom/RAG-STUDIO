#!/usr/bin/env python3
"""Congelamiento del corpus D (AGENTE UDL) para RAG-INC-01a.

Herramienta de evidencia, NO código productivo de RAG Studio. Solo usa la
biblioteca estándar de Python 3 (sin instalar nada).

Garantías:
- NUNCA abre las bases de datos ORIGINALES. Sobre el original solo lee
  bytes para calcular hashes y copiar archivos.
- Copia la carpeta del proyecto y la de sus instantáneas a un destino FUERA
  de la instalación, verifica que la copia es idéntica byte a byte y solo
  entonces analiza la COPIA.
- Si la copia trae un WAL con contenido, lo consolida sobre una SEGUNDA
  copia de trabajo (nunca sobre la copia de evidencia ni sobre el original).
- Al terminar vuelve a calcular los hashes del original y aborta el informe
  si cambió algo durante la ejecución.

Uso (con RAG Studio y cualquier runtime CERRADOS):

    python3 congelar_corpus_D.py \\
        --data "/Users/.../RAG_STUDIO_3/data_AGENTE_UDL" \\
        --project-id 6073eda1-268d-48bd-8257-e6d3fef4f981 \\
        --out "/Users/.../congelamiento_corpus_D_2026-10-14"

Genera en --out:
    evidencia/        copia idéntica del proyecto y de sus instantáneas
    evidencia.tar.gz  la misma copia empaquetada
    informe_corpus_D.json  y  informe_corpus_D.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

_VOLATILES = ("-wal", "-shm", "-journal")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def inventario(base: Path) -> dict[str, dict]:
    """Ruta relativa -> {sha256, bytes}. Incluye -wal/-shm (se reportan aparte)."""
    salida = {}
    for p in sorted(x for x in base.rglob("*") if x.is_file()):
        rel = p.relative_to(base).as_posix()
        salida[rel] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    return salida


def procesos_con_archivos(paths: list[Path]) -> str:
    """Lista de procesos que tienen abiertos archivos de la instalación (lsof, si existe)."""
    if shutil.which("lsof") is None:
        return "lsof no disponible: confirme manualmente que RAG Studio y el runtime están cerrados"
    try:
        r = subprocess.run(["lsof", "+D", *map(str, paths)], capture_output=True, text=True, timeout=120)
        return r.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"no se pudo ejecutar lsof: {exc}"


def consultar(db: Path) -> dict:
    """Consultas de solo lectura sobre una COPIA ya consolidada (immutable=1)."""
    uri = db.resolve().as_uri() + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def uno(sql: str):
            try:
                return con.execute(sql).fetchone()[0]
            except sqlite3.Error as exc:
                return f"error: {exc}"

        def todos(sql: str):
            try:
                cur = con.execute(sql)
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, fila)) for fila in cur.fetchall()]
            except sqlite3.Error as exc:
                return f"error: {exc}"

        return {
            "alembic_version": uno("SELECT version_num FROM alembic_version") if "alembic_version" in tablas else None,
            "proyecto": todos("SELECT id, name, status, created_at, updated_at FROM project"),
            "fuentes": uno("SELECT COUNT(*) FROM source") if "source" in tablas else None,
            "fuentes_por_estado": todos(
                "SELECT validation_status, COUNT(*) AS n FROM source GROUP BY validation_status"
            ) if "source" in tablas else None,
            "fuentes_sin_content_hash": uno(
                "SELECT COUNT(*) FROM source WHERE content_hash IS NULL OR content_hash = ''"
            ) if "source" in tablas else None,
            "fuentes_con_supersedes": uno(
                "SELECT COUNT(*) FROM source WHERE supersedes_source_id IS NOT NULL"
            ) if "source" in tablas else None,
            "chunks": uno("SELECT COUNT(*) FROM chunk") if "chunk" in tablas else None,
            "indice": todos("SELECT * FROM index_info") if "index_info" in tablas else None,
            "instantaneas_registradas": todos(
                "SELECT id, version, snapshot_dir, created_at FROM project_snapshot ORDER BY version"
            ) if "project_snapshot" in tablas else None,
            "integrity_check": uno("PRAGMA integrity_check"),
        }
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="carpeta de datos de la instalación (contiene projects/ y snapshots/)")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--out", required=True, help="carpeta de salida NUEVA, fuera de --data")
    ap.add_argument("--nombre-esperado", default="AGENTE UDL")
    args = ap.parse_args()

    data = Path(args.data).expanduser().resolve()
    proyecto = data / "projects" / args.project_id
    instantaneas = data / "snapshots" / args.project_id
    out = Path(args.out).expanduser().resolve()
    if not proyecto.is_dir():
        sys.exit(f"No existe la carpeta del proyecto: {proyecto}")
    if out.exists():
        sys.exit(f"--out ya existe; use una carpeta nueva: {out}")
    if data == out or data in out.parents:
        sys.exit("--out debe estar FUERA de la carpeta de datos")

    inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
    origenes = [proyecto] + ([instantaneas] if instantaneas.is_dir() else [])
    abiertos = procesos_con_archivos(origenes)
    if abiertos and not abiertos.startswith(("lsof no", "no se pudo")):
        print("ATENCIÓN: hay procesos con archivos abiertos de la instalación:\n" + abiertos)
        print("Cierre RAG Studio y el runtime y vuelva a ejecutar.")
        return 2

    # 1. Inventario del ORIGINAL (solo lectura de bytes).
    inv_proyecto = inventario(proyecto)
    inv_inst = inventario(instantaneas) if instantaneas.is_dir() else {}
    wal = inv_proyecto.get("project.db-wal", {}).get("bytes")

    # 2. Copia de evidencia y verificación byte a byte.
    evidencia = out / "evidencia"
    shutil.copytree(proyecto, evidencia / "projects" / args.project_id, copy_function=shutil.copy2)
    if instantaneas.is_dir():
        shutil.copytree(instantaneas, evidencia / "snapshots" / args.project_id, copy_function=shutil.copy2)
    if inventario(evidencia / "projects" / args.project_id) != inv_proyecto:
        sys.exit("La copia del proyecto no es idéntica al original (¿alguien escribió durante la copia?)")
    if instantaneas.is_dir() and inventario(evidencia / "snapshots" / args.project_id) != inv_inst:
        sys.exit("La copia de instantáneas no es idéntica al original")

    # 3. Copia de trabajo para consultar (consolida el WAL si lo hubiera).
    trabajo = out / "trabajo_consulta"
    trabajo.mkdir(parents=True)
    db_trabajo = trabajo / "project.db"
    for nombre in ("project.db", "project.db-wal", "project.db-shm"):
        origen = evidencia / "projects" / args.project_id / nombre
        if origen.exists():
            shutil.copy2(origen, trabajo / nombre)
    wal_consolidado = False
    if (trabajo / "project.db-wal").exists() and (trabajo / "project.db-wal").stat().st_size > 0:
        con = sqlite3.connect(db_trabajo)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        wal_consolidado = True
    for nombre in ("project.db-wal", "project.db-shm"):
        (trabajo / nombre).unlink(missing_ok=True)
    datos = consultar(db_trabajo)

    nombres = [p.get("name") for p in datos["proyecto"]] if isinstance(datos["proyecto"], list) else []
    ids = [p.get("id") for p in datos["proyecto"]] if isinstance(datos["proyecto"], list) else []
    confirmado = args.project_id in ids and args.nombre_esperado in nombres

    # 4. Instantáneas: identidad y project.db de cada versión.
    detalle_inst = []
    if instantaneas.is_dir():
        for v in sorted(p for p in (evidencia / "snapshots" / args.project_id).iterdir() if p.is_dir()):
            ident = v / "snapshot_identity.json"
            pdb = v / "project.db"
            detalle_inst.append({
                "carpeta": v.name,
                "project_db_sha256": sha256(pdb) if pdb.exists() else None,
                "snapshot_identity_sha256": sha256(ident) if ident.exists() else None,
                "snapshot_identity": json.loads(ident.read_text(encoding="utf-8")) if ident.exists() else None,
            })

    # 5. Registro de lotes.
    lotes_path = evidencia / "projects" / args.project_id / "lotes_importados.jsonl"
    lotes = None
    if lotes_path.exists():
        lineas = [json.loads(x) for x in lotes_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        lotes = {
            "sha256": sha256(lotes_path),
            "registros": len(lineas),
            "lotes": [{"etiqueta": x.get("label"), "huella": x.get("fingerprint"), "relacion": x.get("relation"),
                       "importado_en": x.get("imported_at"), "completo": x.get("complete")} for x in lineas],
        }

    # 6. Paquete de evidencia.
    tar = out / "evidencia.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(evidencia, arcname="evidencia")

    # 7. El original no debe haber cambiado.
    if inventario(proyecto) != inv_proyecto or (instantaneas.is_dir() and inventario(instantaneas) != inv_inst):
        sys.exit("El ORIGINAL cambió durante el congelamiento. Repita con RAG Studio cerrado.")

    informe = {
        "fecha_inicio_utc": inicio,
        "fecha_fin_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equipo": platform.node(), "sistema": platform.platform(), "python": platform.python_version(),
        "ruta_datos": str(data), "ruta_proyecto": str(proyecto), "ruta_instantaneas": str(instantaneas),
        "proyecto_confirmado": confirmado,
        "project_db_sha256": inv_proyecto.get("project.db", {}).get("sha256"),
        "project_db_bytes": inv_proyecto.get("project.db", {}).get("bytes"),
        "wal_bytes_original": wal,
        "wal_consolidado_en_copia_de_trabajo": wal_consolidado,
        "procesos_abiertos": abiertos,
        "consultas": datos,
        "instantaneas": detalle_inst,
        "lotes_importados": lotes,
        "inventario_proyecto": inv_proyecto,
        "inventario_instantaneas": inv_inst,
        "evidencia_tar_gz_sha256": sha256(tar),
    }
    (out / "informe_corpus_D.json").write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8",
    )
    resumen = [
        "# Congelamiento corpus D — AGENTE UDL",
        f"- Proyecto confirmado: {'sí' if confirmado else 'NO'} ({nombres})",
        f"- project.db SHA-256: {informe['project_db_sha256']} ({informe['project_db_bytes']} B)",
        f"- WAL original: {wal} B; consolidado en copia de trabajo: {wal_consolidado}",
        f"- Alembic: {datos['alembic_version']}",
        f"- Fuentes: {datos['fuentes']}; chunks: {datos['chunks']}",
        f"- Instantáneas en disco: {[i['carpeta'] for i in detalle_inst]}",
        f"- Instantáneas registradas: {datos['instantaneas_registradas']}",
        f"- lotes_importados.jsonl: {lotes['sha256'] if lotes else 'no existe'}",
        f"- integrity_check: {datos['integrity_check']}",
        f"- evidencia.tar.gz SHA-256: {informe['evidencia_tar_gz_sha256']}",
        f"- SHA-256 de este informe JSON: {sha256(out / 'informe_corpus_D.json')}",
    ]
    (out / "informe_corpus_D.md").write_text("\n".join(resumen) + "\n", encoding="utf-8")
    print("\n".join(resumen))
    return 0 if confirmado else 3


if __name__ == "__main__":
    sys.exit(main())
