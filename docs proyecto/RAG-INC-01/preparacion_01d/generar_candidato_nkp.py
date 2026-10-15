"""RAG-INC-01d · Fase 1 — paquete NKP candidato a partir de una COPIA de una
instalación ya preparada (migrada a 0021, con huellas completas y, si aplica,
saneada). No toca Runtime ni el origen.

Pasos:
1. Abre la instalación de trabajo (copia) con la aplicación.
2. Publica una instantánea NUEVA del proyecto; las anteriores no se tocan.
3. Exporta el NKP dos veces (carpetas a/ y b/) con la compuerta de 01c, que
   incluye el validador firmado v1.0.0 y la unicidad de RAG Studio.
4. Vuelve a pasar el paquete por el validador firmado vendorizado, en un
   proceso aparte.
5. Comprueba reproducibilidad: mismos ids, conteos, content_digest y
   archivos internos, y ZIP byte a byte.
6. Escribe <out>/informe_candidato.json.

Uso:
  python3 generar_candidato_nkp.py --corpus B --instalacion <copia>/instalacion \
      --project-id <id> --tenant <tenant> --out <carpeta_nueva>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from app.lifecycle import shutdown, start  # noqa: E402
from contracts.nexom_knowledge_package import VALIDATOR_PATH  # noqa: E402
from infrastructure.filesystem.snapshot_identity import content_fingerprint  # noqa: E402


def sha256(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def leer_zip(ruta: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(ruta) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def ids(contenido: dict[str, bytes]) -> dict[str, list[str]]:
    salida = {}
    for nombre in ("sources.jsonl", "chunks.jsonl", "evidence.jsonl", "media.jsonl", "source_metadata.jsonl"):
        salida[nombre] = sorted(json.loads(x)["id"] for x in contenido[nombre].decode().splitlines() if x.strip())
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--instalacion", required=True, type=Path)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"--out debe ser una carpeta nueva: {a.out}")

    ctx = start(base_dir=a.instalacion)
    try:
        proyecto = ctx.project_service.get_project(a.project_id)
        faltantes = ctx.document_service.backfill_content_hashes(a.project_id).missing_after
        previas = [(s.version, s.id) for s in ctx.release_service.list_snapshots(a.project_id)]
        snap = ctx.release_service.publish_snapshot(a.project_id)
        huella_antes = content_fingerprint(snap.snapshot_dir)
        exp_a = ctx.knowledge_package_export.execute(a.project_id, snap.id, a.tenant, str(a.out / "a"))
        exp_b = ctx.knowledge_package_export.execute(a.project_id, snap.id, a.tenant, str(a.out / "b"))
        huella_despues = content_fingerprint(snap.snapshot_dir)
    finally:
        shutdown(ctx)

    za, zb = leer_zip(Path(exp_a.zip_path)), leer_zip(Path(exp_b.zip_path))
    manifest = json.loads(za["manifest.json"])
    ms = json.loads(za["metadata_schema.json"])
    firmado = subprocess.run([sys.executable, str(VALIDATOR_PATH), exp_a.zip_path, "--content-digest-file",
                              exp_a.content_digest_path], capture_output=True, text=True)
    lineas = [x for x in firmado.stdout.splitlines() if x.startswith(("OK:", "ERRORES:"))]
    informe = {
        "corpus": a.corpus,
        "instalacion_de_trabajo": str(a.instalacion),
        "project_id": a.project_id,
        "proyecto": proyecto.name,
        "knowledge_base_id": exp_a.knowledge_base_id,
        "fuentes_sin_huella": faltantes,
        "instantaneas_previas": previas,
        "instantanea_nueva": {"snapshot_id": snap.id, "version": snap.version,
                              "fecha": snap.created_at.isoformat(), "snapshot_dir": snap.snapshot_dir},
        "instantanea_intacta_tras_exportar": huella_antes == huella_despues,
        "package_id": exp_a.package_id,
        "tenant": a.tenant,
        "conteos": exp_a.counts,
        "metadata_schema": {"schema_version_local": ms["schema_version_local"], "fields": len(ms["fields"]),
                            "catalogs": len(ms["catalogs"])},
        "embedding_spaces": json.loads(za["embedding_spaces.json"]),
        "indexes": json.loads(za["indexes.json"]),
        "capabilities": manifest["capabilities"],
        "omissions": [o["code"] for o in manifest["omissions"]],
        "content_digest": exp_a.content_digest,
        "checksums_json_hash": exp_a.checksums_json_hash,
        "zip": Path(exp_a.zip_path).name,
        "zip_sha256": exp_a.zip_sha256,
        "sidecar_sha256": sha256(Path(exp_a.content_digest_path)),
        "compuerta_01c": exp_a.conformance.summary() if exp_a.conformance else None,
        "validador_firmado": {"returncode": firmado.returncode, "resumen": lineas},
        "reproducibilidad": {
            "mismo_package_id": exp_a.package_id == exp_b.package_id,
            "mismo_content_digest": exp_a.content_digest == exp_b.content_digest,
            "mismos_conteos": exp_a.counts == exp_b.counts,
            "mismos_ids_portables": ids(za) == ids(zb),
            "mismos_archivos_internos": za == zb,
            "zip_identico_byte_a_byte": exp_a.zip_sha256 == exp_b.zip_sha256,
        },
    }
    (a.out / "informe_candidato.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("corpus", "package_id", "conteos", "compuerta_01c", "validador_firmado",
                                               "reproducibilidad")}, ensure_ascii=False, indent=1))
    ok = (firmado.returncode == 0 and informe["instantanea_intacta_tras_exportar"]
          and all(informe["reproducibilidad"].values()) and faltantes == 0)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
