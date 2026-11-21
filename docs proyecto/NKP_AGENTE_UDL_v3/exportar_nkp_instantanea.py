"""Exportación NEXOM Knowledge Package (NKP) v1.0.0 CORE de una instantánea YA
PUBLICADA, sin publicar otra y sin abrir la instalación con la aplicación.

Herramienta de operación (no es código del producto): usa el exportador
existente (`infrastructure/exporters/nexom_knowledge_package.py`) tal cual,
incluida su compuerta de conformidad obligatoria (validador firmado v1.0.0).

Garantías:
- No llama a `start()`/`bootstrap()`: no aplica migraciones, no publica
  instantáneas y no escribe en la instalación.
- El registro de la instantánea se lee de una COPIA temporal del project.db
  del proyecto vivo; el exportador, a su vez, lee una copia del project.db de
  la instantánea.
- La huella de la instantánea (`content_fingerprint`) se calcula antes y
  después: si cambia, la ejecución falla.
- Solo escribe en `--salida` (carpeta nueva).

Dos pasos:

  1) verificar  (sin tenant definitivo; no deja paquete)
     python exportar_nkp_instantanea.py verificar --instalacion <RAGSTUDIO_HOME> \
         --project-id <id> --version 3 --huella sha256:<...> --salida <carpeta_nueva>

     Localiza la instantánea por versión, informa su snapshot_id real, comprueba
     la huella y las precondiciones, y ejecuta el exportador completo en una
     carpeta temporal con un tenant de prueba (que se borra) para comprobar que
     todas las compuertas pasan. Escribe <salida>/verificacion.json.

  2) exportar   (requiere el tenant confirmado y el snapshot_id del paso 1)
     python exportar_nkp_instantanea.py exportar --instalacion <RAGSTUDIO_HOME> \
         --project-id <id> --version 3 --snapshot-id <id del paso 1> \
         --huella sha256:<...> --tenant <tenant confirmado> --salida <carpeta_nueva>

     Exporta, valida el ZIP con el validador oficial en un proceso aparte,
     verifica manifest y conteos y escribe evidencia y trazabilidad.
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
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from contracts.nexom_knowledge_package import VALIDATOR_PATH  # noqa: E402
from domain.documents.entities import NON_FILE_SOURCE_TYPES  # noqa: E402
from domain.knowledge_package.entities import CONTRACT_SCHEMA_VERSION, PROFILE_CORE, SnapshotDescriptor  # noqa: E402
from infrastructure.exporters.nexom_knowledge_package import (  # noqa: E402
    EXPORTER_VERSION, NexomKnowledgePackageExporter, package_id_for,
)
from infrastructure.filesystem.paths import InstallationPaths  # noqa: E402
from infrastructure.filesystem.snapshot_identity import (  # noqa: E402
    SnapshotIdentityError, content_fingerprint, read_snapshot_identity,
)

TENANT_DE_PRUEBA = "verificacion-previa-no-entregar"
_NO_ARCHIVO = ", ".join(f"'{t.value}'" for t in sorted(NON_FILE_SOURCE_TYPES, key=lambda t: t.value))


class Detener(Exception):
    """Precondición no cumplida: se informa y no se continúa."""


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _copia_sqlite(origen: Path, destino_dir: Path) -> Path:
    """Copia project.db (y su -wal si existe) para leerla sin tocar el original."""
    destino = destino_dir / "project.db"
    shutil.copy2(origen, destino)
    wal = origen.with_name(origen.name + "-wal")
    if wal.is_file():
        shutil.copy2(wal, destino_dir / "project.db-wal")
    return destino


def _parse_fecha(valor: str) -> datetime:
    fecha = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def localizar_instantanea(instalacion: Path, project_id: str, version: int) -> dict:
    """Registro de la instantánea `version` del proyecto, leído de una copia."""
    db_vivo = InstallationPaths(instalacion).project_db_path(project_id)
    if not db_vivo.is_file():
        raise Detener(f"No existe el project.db del proyecto {project_id} en {db_vivo}.")
    with tempfile.TemporaryDirectory(prefix="nkp-registro-") as tmp:
        con = sqlite3.connect(_copia_sqlite(db_vivo, Path(tmp)))
        con.row_factory = sqlite3.Row
        try:
            filas = [dict(r) for r in con.execute(
                "SELECT id, project_id, version, snapshot_dir, created_at FROM project_snapshot "
                "WHERE project_id = ? ORDER BY version", (project_id,))]
            proyecto = con.execute("SELECT name FROM project WHERE id = ?", (project_id,)).fetchone()
        finally:
            con.close()
    elegidas = [f for f in filas if int(f["version"]) == version]
    if len(elegidas) != 1:
        raise Detener(f"Se esperaba exactamente una instantánea v{version}; hay {len(elegidas)}. "
                      f"Registradas: {[(f['version'], f['id']) for f in filas]}.")
    registro = elegidas[0]
    registro["proyecto"] = proyecto["name"] if proyecto else None
    registro["registradas"] = [{"version": f["version"], "snapshot_id": f["id"]} for f in filas]
    return registro


def precondiciones(registro: dict, huella_esperada: str) -> dict:
    carpeta = Path(registro["snapshot_dir"])
    if not (carpeta / "project.db").is_file():
        raise Detener(f"La carpeta de la instantánea no existe o no tiene project.db: {carpeta}.")
    huella = content_fingerprint(carpeta)
    try:
        identidad = read_snapshot_identity(carpeta)
    except (SnapshotIdentityError, OSError):
        identidad = None
    datos = {
        "snapshot_dir": str(carpeta),
        "huella_calculada": huella,
        "huella_declarada": identidad.content_fingerprint if identidad else None,
        "huella_esperada": huella_esperada,
    }
    if huella != huella_esperada:
        raise Detener(f"La huella de la instantánea ({huella}) no coincide con la validada ({huella_esperada}).")
    with tempfile.TemporaryDirectory(prefix="nkp-precond-") as tmp:
        con = sqlite3.connect(_copia_sqlite(carpeta / "project.db", Path(tmp)))
        con.row_factory = sqlite3.Row
        try:
            cols_proyecto = {r[1] for r in con.execute("PRAGMA table_info(project)")}
            cols_fuente = {r[1] for r in con.execute("PRAGMA table_info(source)")}
            pid = registro["project_id"]
            uno = lambda sql: con.execute(sql, (pid,)).fetchone()[0]  # noqa: E731
            datos.update({
                "alembic_version": con.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "identidades_0021": "knowledge_base_id" in cols_proyecto and "lineage_id" in cols_fuente,
                "knowledge_base_id": (con.execute("SELECT knowledge_base_id FROM project WHERE id = ?", (pid,)).fetchone()
                                      or [None])[0] if "knowledge_base_id" in cols_proyecto else None,
                "fuentes": uno("SELECT COUNT(*) FROM source WHERE project_id = ?"),
                "fuentes_de_archivo_sin_content_hash": uno(
                    "SELECT COUNT(*) FROM source WHERE project_id = ? AND (content_hash IS NULL OR content_hash = '') "
                    f"AND source_type NOT IN ({_NO_ARCHIVO})"),
                "fragmentos": uno("SELECT COUNT(*) FROM chunk WHERE project_id = ?"),
                "intenciones": uno("SELECT COUNT(*) FROM intent WHERE project_id = ?"),
                "reglas": uno("SELECT COUNT(*) FROM guardrail_rule WHERE project_id = ?"),
                "indice": dict(con.execute(
                    "SELECT embedding_provider, embedding_model, dimensions, points_count FROM index_info "
                    "WHERE project_id = ?", (pid,)).fetchone() or {}),
                "procedimiento_recuperacion": (con.execute(
                    "SELECT value FROM configuration WHERE project_id = ? AND key = 'retrieval_procedure' "
                    "ORDER BY version DESC LIMIT 1", (pid,)).fetchone() or ["(sin ajuste: r105b)"])[0],
            })
        finally:
            con.close()
    if not datos["identidades_0021"]:
        raise Detener("La instantánea es anterior a la migración 0021 (sin identidades persistentes).")
    return datos


def _descriptor(registro: dict) -> SnapshotDescriptor:
    return SnapshotDescriptor(
        id=registro["id"], project_id=registro["project_id"], version=int(registro["version"]),
        snapshot_dir=registro["snapshot_dir"], created_at=_parse_fecha(registro["created_at"]),
    )


def _validar_oficial(zip_path: Path, sidecar: Path) -> dict:
    r = subprocess.run([sys.executable, str(VALIDATOR_PATH), str(zip_path), "--content-digest-file", str(sidecar)],
                       capture_output=True, text=True, timeout=600)
    salida = r.stdout + r.stderr
    resumen = [x for x in salida.splitlines() if x.startswith(("OK:", "ERRORES:"))]
    return {"returncode": r.returncode, "resumen": resumen,
            "errores_0": r.returncode == 0 and any(x.strip() == "ERRORES: 0" for x in resumen), "salida": salida}


def verificar(a) -> int:
    registro = localizar_instantanea(a.instalacion, a.project_id, a.version)
    datos = precondiciones(registro, a.huella)
    with tempfile.TemporaryDirectory(prefix="nkp-ensayo-") as tmp:
        resultado = NexomKnowledgePackageExporter().export(_descriptor(registro), TENANT_DE_PRUEBA, str(Path(tmp) / "x"))
        ensayo = {"compuertas": "PASS", "conteos": resultado.counts,
                  "conformidad": resultado.conformance.summary() if resultado.conformance else None}
    huella_despues = content_fingerprint(registro["snapshot_dir"])
    informe = {
        "proyecto": registro["proyecto"], "project_id": registro["project_id"],
        "version": registro["version"], "snapshot_id": registro["id"], "created_at": registro["created_at"],
        "instantaneas_registradas": registro["registradas"], "precondiciones": datos,
        "ensayo_exportador_con_tenant_de_prueba": ensayo,
        "instantanea_intacta": huella_despues == datos["huella_calculada"],
        "codigo": {"exporter_version": EXPORTER_VERSION, "schema_version": CONTRACT_SCHEMA_VERSION},
    }
    a.salida.mkdir(parents=True, exist_ok=False)
    (a.salida / "verificacion.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    print("PRECONDICIONES: OK" if informe["instantanea_intacta"] else "PRECONDICIONES: FALLA")
    return 0 if informe["instantanea_intacta"] else 1


def exportar(a) -> int:
    registro = localizar_instantanea(a.instalacion, a.project_id, a.version)
    if registro["id"] != a.snapshot_id:
        raise Detener(f"El snapshot_id de la v{a.version} es {registro['id']}, no el indicado ({a.snapshot_id}).")
    tenant = (a.tenant or "").strip()
    if not tenant or tenant == TENANT_DE_PRUEBA:
        raise Detener("Falta el tenant confirmado.")
    datos = precondiciones(registro, a.huella)
    a.salida.mkdir(parents=True, exist_ok=False)
    resultado = NexomKnowledgePackageExporter().export(_descriptor(registro), tenant, str(a.salida))
    huella_despues = content_fingerprint(registro["snapshot_dir"])
    zip_path, sidecar = Path(resultado.zip_path), Path(resultado.content_digest_path)
    oficial = _validar_oficial(zip_path, sidecar)
    (a.salida / "validacion_oficial.txt").write_text(oficial.pop("salida"), encoding="utf-8")
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        chunks_zip = sum(1 for x in zf.read("chunks.jsonl").decode().splitlines() if x.strip())
        fuentes_zip = sum(1 for x in zf.read("sources.jsonl").decode().splitlines() if x.strip())
    comprobaciones = {
        "schema_version == 1.0.0": manifest["schema_version"] == "1.0.0",
        "profile == CORE": manifest["profile"] == PROFILE_CORE,
        "project_id_origin": manifest["project_id_origin"] == a.project_id,
        "snapshot_id": manifest["snapshot_id"] == registro["id"],
        "knowledge_version": manifest["knowledge_version"] == str(registro["version"]),
        "knowledge_base_id": manifest["knowledge_base_id"] == datos["knowledge_base_id"],
        "tenant": manifest["tenant"] == tenant,
        "package_id": manifest["package_id"] == package_id_for(datos["knowledge_base_id"], registro["id"], tenant),
        "fuentes (manifest = archivo = instantánea)": manifest["counts"]["sources"] == fuentes_zip == datos["fuentes"],
        "fragmentos (manifest = archivo = instantánea)": manifest["counts"]["chunks"] == chunks_zip == datos["fragmentos"],
        "intenciones": manifest["counts"]["intents"] == datos["intenciones"],
        "reglas": manifest["counts"]["guardrail_rules"] == datos["reglas"],
        "validador oficial ERRORES: 0": oficial["errores_0"],
        "instantánea intacta": huella_despues == datos["huella_calculada"],
    }
    trazabilidad = {
        "proyecto": registro["proyecto"], "project_id": a.project_id, "knowledge_base_id": datos["knowledge_base_id"],
        "instantanea": {"version": registro["version"], "snapshot_id": registro["id"],
                        "created_at": registro["created_at"], "huella": datos["huella_calculada"],
                        "huella_declarada": datos["huella_declarada"],
                        "procedimiento_recuperacion": datos["procedimiento_recuperacion"]},
        "paquete": {"package_id": resultado.package_id, "tenant": tenant, "schema_version": manifest["schema_version"],
                    "profile": manifest["profile"], "exporter_version": manifest["exporter_version"],
                    "content_digest": resultado.content_digest, "checksums_json_sha256": resultado.checksums_json_hash,
                    "zip": zip_path.name, "zip_sha256": resultado.zip_sha256, "sidecar": sidecar.name,
                    "sidecar_sha256": _sha256(sidecar), "counts": manifest["counts"],
                    "omissions": [o["code"] for o in manifest["omissions"]]},
        "indice_en_rag_studio": datos["indice"],
        "validacion_oficial": oficial,
        "comprobaciones": comprobaciones,
        "resultado": "PASS" if all(comprobaciones.values()) else "FAIL",
    }
    (a.salida / "trazabilidad.json").write_text(json.dumps(trazabilidad, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps(trazabilidad, ensure_ascii=False, indent=2))
    print(trazabilidad["resultado"])
    return 0 if trazabilidad["resultado"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["verificar", "exportar"])
    ap.add_argument("--instalacion", required=True, type=Path, help="RAGSTUDIO_HOME")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--version", required=True, type=int)
    ap.add_argument("--huella", required=True, help="sha256:... validada")
    ap.add_argument("--snapshot-id")
    ap.add_argument("--tenant")
    ap.add_argument("--salida", required=True, type=Path, help="carpeta nueva")
    a = ap.parse_args()
    if a.salida.exists():
        print(f"DETENIDO: --salida debe ser una carpeta nueva ({a.salida}).")
        return 2
    try:
        return verificar(a) if a.modo == "verificar" else exportar(a)
    except Detener as exc:
        print(f"DETENIDO (precondición): {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
