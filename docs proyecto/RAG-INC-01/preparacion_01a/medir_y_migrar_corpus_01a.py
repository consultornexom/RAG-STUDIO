#!/usr/bin/env python3
"""RAG-INC-01a — aplica la migración 0021 sobre una COPIA de un corpus y
registra las mediciones X-01, X-02, X-03, M-05b e INC01-R6.

Herramienta de evidencia (no es código productivo). Se ejecuta desde la raíz
del código de RAG Studio, porque usa sus migraciones:

    python3 "docs proyecto/RAG-INC-01/preparacion_01a/medir_y_migrar_corpus_01a.py" \\
        --corpus C --origen PRUEBAS_.../Prueba_B_Cobertura_OCR_25_programas.agentproj \\
        --sha256-origen 0915...4eaa7 --out /tmp/corpus_C

--origen admite:
  * un .agentproj (ZIP con project.db en la raíz);
  * un .tar.gz de congelamiento (`evidencia/projects/<id>/project.db`);
  * una carpeta de proyecto con project.db.

Nunca escribe en el origen: verifica su SHA-256, extrae/copia project.db a
--out y trabaja solo sobre esa copia. Si la copia está antes de 0020, la
lleva a 0020 y la congela aparte antes de aplicar 0021
(Congelamiento_Corpus_UDL.md, sección 3).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import sys
import tarfile
import zipfile
from pathlib import Path

RAIZ_CODIGO = Path.cwd()
CONSULTAS = Path(__file__).with_name("consultas_medicion_01a.sql")
ID_SCHEME = (Path(__file__).resolve().parents[2] / "NEXOM_Knowledge_Package_v1" / "contrato_v1.0.0"
             / "common" / "id_scheme.py")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def obtener_copia(origen: Path, out: Path) -> Path:
    destino = out / "copia_original" / "project.db"
    destino.parent.mkdir(parents=True)
    if origen.is_dir():
        shutil.copy2(origen / "project.db", destino)
        for aux in ("project.db-wal",):
            if (origen / aux).exists() and (origen / aux).stat().st_size > 0:
                sys.exit("El origen tiene un WAL con contenido: obtener primero una copia consistente")
    elif origen.name.endswith(".tar.gz"):
        with tarfile.open(origen) as tf:
            miembros = [m for m in tf.getmembers() if m.name.endswith("/project.db") and "/projects/" in m.name]
            if len(miembros) != 1:
                sys.exit(f"Se esperaba exactamente un projects/<id>/project.db en {origen}")
            with tf.extractfile(miembros[0]) as f, destino.open("wb") as d:  # type: ignore[union-attr]
                shutil.copyfileobj(f, d)
    else:
        with zipfile.ZipFile(origen) as zf, zf.open("project.db") as f, destino.open("wb") as d:
            shutil.copyfileobj(f, d)
    return destino


def leer(db: Path, sql: str):
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    finally:
        con.close()


def consultas_nombradas() -> dict[str, str]:
    """Bloques de consultas_medicion_01a.sql por su etiqueta ("0.", "1a."...)."""
    texto = CONSULTAS.read_text(encoding="utf-8")
    bloques: dict[str, str] = {}
    etiqueta, actual = None, []
    for linea in texto.splitlines():
        if linea.startswith("-- ") and len(linea) > 3 and linea[3].isdigit() and "." in linea[3:7]:
            if etiqueta and actual:
                bloques[etiqueta] = "\n".join(actual)
            etiqueta, actual = linea[3:].split(".")[0], []
            continue
        if linea.startswith("SELECT") and etiqueta is None:
            etiqueta = "0"
        if not linea.startswith("--") and etiqueta is not None:
            actual.append(linea)
        if linea.rstrip().endswith(";") and etiqueta is not None:
            bloques[etiqueta] = "\n".join(actual)
            etiqueta, actual = None, []
    if etiqueta is None and "SELECT version_num FROM alembic_version;" in texto:
        bloques.setdefault("0", "SELECT version_num FROM alembic_version;")
    return bloques


def mediciones(db: Path) -> dict:
    b = consultas_nombradas()
    r = {k: leer(db, v) for k, v in b.items() if k in {"1a", "1b", "1c", "2a", "2b", "2c", "2d", "2e"}}
    r["0"] = leer(db, "SELECT version_num FROM alembic_version")
    # INC01-R1 (X-02): consulta del archivo, sin etiqueta numerada.
    r["R1"] = leer(db, "SELECT COUNT(*) AS fuentes_sin_content_hash FROM source WHERE content_hash IS NULL")
    if not r["2d"]:  # 2f-2h solo sin ciclos
        for k in ("2f", "2g", "2h"):
            r[k] = leer(db, b[k])
    return r


def cargar_id_scheme():
    spec = importlib.util.spec_from_file_location("id_scheme", ID_SCHEME)
    modulo = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(modulo)  # type: ignore[union-attr]
    return modulo


def colisiones_portables(db: Path) -> dict:
    """M-05b: ids portables duplicados (source.id y chunk.id) con las fórmulas
    normativas de id_scheme.py. `updated_at` se usa tal como está guardado
    (solo afecta a fuentes sin content_hash; aproximación documentada)."""
    ids = cargar_id_scheme()
    fuentes = leer(db, "SELECT id, lineage_id, content_hash, title, source_type, updated_at FROM source")
    por_portable: dict[str, list[str]] = {}
    portable_de: dict[str, str] = {}
    for f in fuentes:
        vk = ids.source_version_key(f["content_hash"], f["title"], f["source_type"], str(f["updated_at"]))
        pid = ids.portable_source_id(f["lineage_id"], vk)
        portable_de[f["id"]] = pid
        por_portable.setdefault(pid, []).append(f["id"])
    col_src = {k: v for k, v in por_portable.items() if len(v) > 1}
    chunks = leer(db, "SELECT id, source_id, chunk_index, text FROM chunk")
    por_chunk: dict[str, list[str]] = {}
    for c in chunks:
        if c["source_id"] in portable_de:
            cid = ids.portable_chunk_id(portable_de[c["source_id"]], c["chunk_index"], c["text"])
            por_chunk.setdefault(cid, []).append(c["id"])
    col_chunk = {k: v for k, v in por_chunk.items() if len(v) > 1}
    return {
        "colisiones_source": [{"portable": k, "locales": v} for k, v in col_src.items()],
        "colisiones_chunk": [{"portable": k, "locales": v} for k, v in col_chunk.items()],
        "chunks_huerfanos": sum(1 for c in chunks if c["source_id"] not in portable_de),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--origen", required=True)
    ap.add_argument("--sha256-origen", required=True)
    ap.add_argument("--sha256-project-db", default=None, help="hash congelado de project.db (si aplica)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(RAIZ_CODIGO))
    from infrastructure.database import migrations as mig  # noqa: E402

    origen, out = Path(args.origen), Path(args.out)
    if out.exists():
        sys.exit(f"--out ya existe: {out}")
    if origen.is_file() and sha256(origen) != args.sha256_origen:
        sys.exit("El SHA-256 del origen no coincide con el congelado")
    if origen.is_dir() and sha256(origen / "project.db") != args.sha256_origen:
        sys.exit("El SHA-256 de project.db del origen no coincide con el congelado")

    copia = obtener_copia(origen, out)
    informe: dict = {"corpus": args.corpus, "origen": str(origen), "sha256_origen": args.sha256_origen,
                     "sha256_copia_project_db": sha256(copia)}
    if args.sha256_project_db and informe["sha256_copia_project_db"] != args.sha256_project_db:
        sys.exit("La copia de project.db no coincide con el hash congelado")

    trabajo = out / "trabajo" / "project.db"
    trabajo.parent.mkdir(parents=True)
    shutil.copy2(copia, trabajo)
    informe["alembic_inicial"] = leer(trabajo, "SELECT version_num FROM alembic_version")[0]["version_num"]
    if informe["alembic_inicial"] != "0020":
        mig.upgrade_project(trabajo, "0020")
        informe["linea_base_0020_sha256"] = sha256(trabajo)
        shutil.copy2(trabajo, out / "linea_base_0020_project.db")
    informe["antes"] = mediciones(trabajo)
    informe["integrity_check_antes"] = leer(trabajo, "PRAGMA integrity_check")[0]["integrity_check"]
    ids_antes = leer(trabajo, "SELECT id, project_id, supersedes_source_id FROM source ORDER BY id")
    chunks_antes = leer(trabajo, "SELECT id, source_id, project_id FROM chunk ORDER BY id")
    proyecto_antes = leer(trabajo, "SELECT id FROM project")

    try:
        mig.upgrade_project(trabajo)
        informe["migracion"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        informe["migracion"] = f"FAIL: {type(exc).__name__}: {exc}"
        informe["alembic_final"] = leer(trabajo, "SELECT version_num FROM alembic_version")[0]["version_num"]
        (out / "informe.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False, default=str))
        print(json.dumps({k: informe[k] for k in ("corpus", "migracion", "alembic_final")}, ensure_ascii=False))
        return 1

    informe["alembic_final"] = leer(trabajo, "SELECT version_num FROM alembic_version")[0]["version_num"]
    informe["proyecto"] = leer(trabajo, "SELECT id, name, knowledge_base_id FROM project")
    informe["fuentes"] = leer(trabajo, "SELECT COUNT(*) AS n FROM source")[0]["n"]
    informe["chunks"] = leer(trabajo, "SELECT COUNT(*) AS n FROM chunk")[0]["n"]
    informe["lineage_distintos"] = leer(trabajo, "SELECT COUNT(DISTINCT lineage_id) AS n FROM source")[0]["n"]
    informe["lineage_nulos"] = leer(trabajo, "SELECT COUNT(*) AS n FROM source WHERE lineage_id IS NULL")[0]["n"]
    informe["knowledge_base_id_nulos"] = leer(
        trabajo, "SELECT COUNT(*) AS n FROM project WHERE knowledge_base_id IS NULL")[0]["n"]
    informe["cadenas_con_lineage_distinto"] = leer(trabajo, (
        "SELECT COUNT(*) AS n FROM source s JOIN source p ON p.id = s.supersedes_source_id "
        "WHERE s.lineage_id <> p.lineage_id"))[0]["n"]
    informe["ciclos"] = len(informe["antes"]["2d"])
    informe["project_id_sin_cambio"] = leer(trabajo, "SELECT id FROM project") == proyecto_antes
    informe["ids_fuente_sin_cambio"] = leer(
        trabajo, "SELECT id, project_id, supersedes_source_id FROM source ORDER BY id") == ids_antes
    informe["ids_chunk_sin_cambio"] = leer(trabajo, "SELECT id, source_id, project_id FROM chunk ORDER BY id") == chunks_antes
    informe["not_null"] = {
        "project.knowledge_base_id": [r for r in leer(trabajo, "PRAGMA table_info(project)")
                                       if r["name"] == "knowledge_base_id"][0]["notnull"] == 1,
        "source.lineage_id": [r for r in leer(trabajo, "PRAGMA table_info(source)")
                              if r["name"] == "lineage_id"][0]["notnull"] == 1,
    }
    informe["integrity_check_despues"] = leer(trabajo, "PRAGMA integrity_check")[0]["integrity_check"]
    informe["m05b"] = colisiones_portables(trabajo)
    informe["sha256_migrado"] = sha256(trabajo)
    informe["origen_sin_cambio"] = (sha256(origen) if origen.is_file() else sha256(origen / "project.db")) \
        == args.sha256_origen
    (out / "informe.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False, default=str))
    resumen = {k: informe[k] for k in (
        "corpus", "alembic_inicial", "alembic_final", "migracion", "fuentes", "chunks", "lineage_distintos",
        "lineage_nulos", "knowledge_base_id_nulos", "ciclos", "cadenas_con_lineage_distinto",
        "project_id_sin_cambio", "ids_fuente_sin_cambio", "ids_chunk_sin_cambio", "not_null",
        "integrity_check_despues", "origen_sin_cambio")}
    resumen["knowledge_base_id"] = [p["knowledge_base_id"] for p in informe["proyecto"]]
    resumen["colisiones_source"] = len(informe["m05b"]["colisiones_source"])
    resumen["colisiones_chunk"] = len(informe["m05b"]["colisiones_chunk"])
    print(json.dumps(resumen, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
