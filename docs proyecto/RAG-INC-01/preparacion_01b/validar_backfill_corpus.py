"""RAG-INC-01 — validación real del relleno de content_hash (INC01-R1,
opción B) sobre una COPIA verificada de un corpus. Nunca toca el origen.

Uso:
  python3 validar_backfill_corpus.py --corpus A --origen <dir_proyecto | paquete.agentproj> \
      --sha256-origen <sha256 de project.db (dir) o del .agentproj> --out <carpeta_nueva> \
      [--correccion-test-case <registro_correccion.json>]

Pasos:
1. Verifica el SHA-256 del origen.
2. Crea una instalación temporal en <out>/instalacion y copia/extrae el
   proyecto en projects/<project_id>/ (B: aplica a la COPIA la corrección de
   códigos de caso de prueba autorizada por NEXOM para 0017).
3. Registra el proyecto (las migraciones pendientes, incluida 0021, corren
   sobre la copia) y ejecuta DocumentService.backfill_content_hashes.
4. Comprueba cada hash escrito contra el SHA-256 de su copia del original,
   que updated_at/lineage_id no cambiaron, la idempotencia (2.ª ejecución) y
   que el origen sigue intacto. Escribe <out>/informe_backfill.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.lifecycle import shutdown, start  # noqa: E402
from infrastructure.database.repositories import SqlAlchemyProjectRepository  # noqa: E402
from infrastructure.filesystem.paths import InstallationPaths  # noqa: E402


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def filas(db: Path) -> dict:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {r[0]: {"hash": r[1], "lineage": r[2], "updated_at": r[3], "tipo": r[4]}
                for r in con.execute("SELECT id, content_hash, lineage_id, updated_at, source_type FROM source")}
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--origen", required=True, type=Path)
    ap.add_argument("--sha256-origen", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--correccion-test-case", type=Path)
    a = ap.parse_args()

    if a.out.exists():
        raise SystemExit(f"--out debe ser una carpeta nueva: {a.out}")
    archivo_hash = a.origen / "project.db" if a.origen.is_dir() else a.origen
    sha_origen = sha256(archivo_hash)
    if sha_origen != a.sha256_origen:
        raise SystemExit(f"SHA-256 del origen no coincide: {sha_origen}")

    paths = InstallationPaths(a.out / "instalacion")
    paths.ensure_installation_layout()
    temporal = a.out / "extraido"
    if a.origen.is_dir():
        shutil.copytree(a.origen, temporal)
    else:
        with zipfile.ZipFile(a.origen) as zf:
            zf.extractall(temporal)
    con = sqlite3.connect(temporal / "project.db")
    pid = con.execute("SELECT id FROM project").fetchone()[0]
    correccion = []
    if a.correccion_test_case:
        correccion = json.loads(a.correccion_test_case.read_text(encoding="utf-8"))
        for c in correccion:
            con.execute("UPDATE test_case SET code = ? WHERE id = ? AND code = ?",
                        (c["code_nuevo"], c["id"], c["code_anterior"]))
        con.commit()
    con.close()
    shutil.move(str(temporal), str(paths.project_dir(pid)))

    repo = SqlAlchemyProjectRepository(paths)
    proyecto = repo.get(pid)  # migra la COPIA hasta head (0021)
    if proyecto is None:
        raise SystemExit(f"La copia no contiene el proyecto {pid}")
    repo.save(proyecto)
    db = paths.project_db_path(pid)
    antes = filas(db)

    ctx = start(base_dir=paths.base_dir)
    try:
        informe = ctx.document_service.backfill_content_hashes(pid)
        segundo = ctx.document_service.backfill_content_hashes(pid)
    finally:
        shutdown(ctx)
    despues = filas(db)

    original_dir = paths.project_dir(pid) / "sources" / "original"
    verificacion = []
    for sid, f in despues.items():
        if antes[sid]["hash"] is None and f["hash"]:
            copia = next(p for p in original_dir.iterdir() if p.name == sid or p.name.startswith(sid + "."))
            verificacion.append(f["hash"] == sha256(copia))
    resultado = {
        "corpus": a.corpus,
        "origen": str(a.origen),
        "sha256_origen": sha_origen,
        "project_id": pid,
        "correccion_test_case_en_copia": correccion,
        "fuentes": len(despues),
        "faltantes_antes": informe.missing_before,
        "faltantes_despues": informe.missing_after,
        "conteos": informe.counts(),
        "escritura": informe.write_outcome,
        "hashes_verificados_contra_copia": f"{sum(verificacion)}/{len(verificacion)}",
        "updated_at_sin_cambio": all(despues[s]["updated_at"] == antes[s]["updated_at"] for s in antes),
        "lineage_sin_cambio": all(despues[s]["lineage"] == antes[s]["lineage"] for s in antes),
        "segunda_ejecucion": {"escritura": segundo.write_outcome, "conteos": segundo.counts()},
        "integrity_check": sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0],
        "informe_servicio": informe.report_path,
        "origen_sin_cambio": sha256(archivo_hash) == sha_origen,
    }
    (a.out / "informe_backfill.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    ok = (resultado["faltantes_despues"] == 0 and resultado["origen_sin_cambio"] and all(verificacion)
          and resultado["updated_at_sin_cambio"] and resultado["lineage_sin_cambio"]
          and segundo.write_outcome == "sin_cambios")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
