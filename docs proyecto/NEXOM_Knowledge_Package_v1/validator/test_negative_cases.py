#!/usr/bin/env python3
"""Suite de pruebas negativas AUTOMATIZADA -- NEXOM Knowledge Package v1.0-rc3.2.

Reproduce, como aserciones ejecutables (no como prosa), los 12 casos
negativos numerados en el tercer veredicto NEXOM, los 4 casos que el propio
revisor demostro manualmente que el validador rc2 aceptaba en silencio, los
casos que la auditoria independiente sobre rc3 demostro que seguia
aceptando (`source.id` que no cumple la formula determinista,
`must_not_retrieve` con un id inexistente, `expected_chunk_id`/
`expected_evidence_id` por encima del nivel de acceso de la prueba con
`expected_source_ids` vacio para evadir el chequeo), y (rc3.2) el caso que
la siguiente auditoria demostro que rc3.1 seguia aceptando: una evidencia
cuyo `chunk_id` sigue apuntando a un chunk confidencial pero cuyo
`source_id` se falsea a una fuente publica.

Cada caso parte de una copia MUTADA del paquete de ejemplo valido
(`example_package/`, regenerado para rc3.2) y afirma que el validador de
referencia lo RECHAZA (codigo de salida 1, al menos 1 error). Los casos que
tocan contenido cubierto por checksums.json recalculan los checksums tras
mutar (usando id_scheme.py, la misma implementacion de referencia que usa
el generador) para que el UNICO defecto presente en el paquete sea el que
el caso pretende probar -- de lo contrario un simple mismatch de checksum
enmascararia si la verificacion especifica tambien funciona. Al final se
corre tambien el caso BASE (sin mutar) y se afirma que se ACEPTA (codigo 0).

Requiere que `example_package/` ya este generado y en estado valido
(`python3 generate_example.py common example_package delivery`).

Uso:
    python3 validator/test_negative_cases.py

Codigo de salida: 0 si todas las aserciones (19 negativas + 1 positiva) se
cumplen, 1 si alguna fallo (paquete que debia rechazarse fue aceptado, o
viceversa) -- pensado para correr en CI.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_PKG = ROOT / "example_package"
DELIVERY = ROOT / "delivery"
VALIDATOR = ROOT / "validator" / "validate_knowledge_package.py"
WORKDIR = Path("/tmp/nkp_negative_cases")

sys.path.insert(0, str(ROOT / "common"))
import id_scheme as k  # noqa: E402


def _discover_delivery_files() -> tuple[Path, Path, Path]:
    """Descubre los sidecars por SUFIJO, no por nombre de version
    hardcodeado -- asi este script no vuelve a quedar desalineado con
    generate_example.py cada vez que cambia el numero de version (rc3.2:
    correccion documental menor 'la version esta hardcodeada en varios
    lugares')."""
    digest = next(DELIVERY.glob("*.content.sha256"))
    stem = digest.name[: -len(".content.sha256")]
    return digest, DELIVERY / f"{stem}.sig", DELIVERY / f"{stem}.pubkey_DEMO.pem"


CONTENT_DIGEST_FILE, SIGNATURE_FILE, PUBLIC_KEY_FILE = _discover_delivery_files()


def run_validator(target: Path, extra_args: list[str] | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(VALIDATOR), str(target)] + (extra_args or [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def fresh_copy(name: str) -> Path:
    dest = WORKDIR / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE_PKG, dest)
    return dest


def rewrite_jsonl(path: Path, mutate_first_record) -> None:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    records = [json.loads(l) for l in lines]
    mutate_first_record(records)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def rewrite_json(path: Path, mutate) -> None:
    obj = json.loads(path.read_text(encoding="utf-8"))
    mutate(obj)
    path.write_text(json.dumps(obj), encoding="utf-8")


def load_jsonl(d: Path, name: str) -> list[dict]:
    return [json.loads(l) for l in (d / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def save_jsonl(d: Path, name: str, recs: list[dict], sort_key: str = "id") -> None:
    (d / name).write_text(
        "\n".join(json.dumps(r) for r in sorted(recs, key=lambda r: r.get(sort_key, ""))) + "\n", encoding="utf-8"
    )


CHECKSUMMED_FILES = [
    "sources.jsonl", "chunks.jsonl", "source_metadata.jsonl", "metadata_schema.json",
    "evidence.jsonl", "media.jsonl", "conversational_bundle.json", "embedding_spaces.json",
    "indexes.json", "acceptance_cases.jsonl", "access_hierarchy.json", "manifest.json",
]


def recompute_checksums(d: Path) -> None:
    """Recalcula checksums.json a partir del contenido ACTUAL de los archivos
    -- usado tras mutar un paquete cuando el caso negativo debe aislar un
    defecto especifico (referencial/semantico) del ruido de un checksum
    desactualizado, que por si solo ya haria que el validador rechace el
    paquete por una razon distinta a la que el caso pretende probar."""

    def recompute_hash(fname: str, data: bytes) -> str:
        if fname.endswith(".jsonl"):
            recs = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
            sort_key = "case_id" if fname == "acceptance_cases.jsonl" else "id"
            return k.sha256_hex(k.canonical_jsonl_bytes(recs, sort_key=sort_key))
        obj = json.loads(data.decode("utf-8"))
        return k.sha256_hex(k.canonical_json_bytes(obj))

    checksums = {"algorithm": "sha256", "canonicalization": "rfc8785", "files": {}}
    for fname in CHECKSUMMED_FILES:
        checksums["files"][fname] = recompute_hash(fname, (d / fname).read_bytes())
    (d / "checksums.json").write_bytes(k.canonical_json_bytes(checksums))


# ---------------------------------------------------------------------------
# Casos negativos 1-4: los 4 que el revisor demostro manualmente que rc2
# aceptaba en silencio (0 errores de schema).
# ---------------------------------------------------------------------------

def case_01_invalid_date(d: Path) -> None:
    rewrite_jsonl(d / "sources.jsonl", lambda recs: recs.__setitem__(0, {**recs[0], "created_at": "not-a-date"}))


def case_02_false_omission_reason_null(d: Path) -> None:
    rewrite_jsonl(d / "sources.jsonl", lambda recs: recs.__setitem__(0, {**recs[0], "original_omission_reason": None}))


def case_03_false_media_included_without_binary(d: Path) -> None:
    rewrite_jsonl(d / "media.jsonl", lambda recs: recs.__setitem__(0, {**recs[0], "included_in_package": True}))


def case_04_false_manifest_count(d: Path) -> None:
    rewrite_json(d / "manifest.json", lambda m: m["counts"].__setitem__("chunks", 999))


# ---------------------------------------------------------------------------
# Casos negativos 5-12: los 8 restantes del listado numerado del tercer
# veredicto (correcciones bloqueantes de rc3).
# ---------------------------------------------------------------------------

def case_05_declared_but_absent_asset(d: Path) -> None:
    # manifest.files declara un archivo que no existe fisicamente.
    rewrite_json(d / "manifest.json", lambda m: m["files"].append("assets/originals/fantasma.pdf"))


def case_06_asset_present_without_checksum(d: Path) -> None:
    # Un archivo fisico + declarado en manifest.files, pero SIN entrada en checksums.json.
    extra = d / "extra_no_checksum.json"
    extra.write_text('{"nota": "archivo real pero sin checksum declarado"}', encoding="utf-8")
    rewrite_json(d / "manifest.json", lambda m: m["files"].append("extra_no_checksum.json"))


def case_07_extra_file_in_directory(d: Path) -> None:
    # Archivo fisico presente pero NO declarado en manifest.files ni en checksums.json.
    (d / "archivo_no_declarado.txt").write_text("intruso", encoding="utf-8")


def case_08_duplicate_entry_inside_zip(_: Path) -> Path:
    # Caso especifico de ZIP: dos entradas con el MISMO nombre dentro del .zip.
    zpath = WORKDIR / "case_08_duplicate.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for f in BASE_PKG.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(BASE_PKG))
        # Segunda entrada duplicada para manifest.json (mismo nombre).
        zf.writestr("manifest.json", (BASE_PKG / "manifest.json").read_bytes())
    return zpath


def case_09_sidecar_not_conforming_to_schema(_: Path) -> Path:
    # signature.json real pero le falta un campo requerido por signature.schema.json.
    sig = json.loads(SIGNATURE_FILE.read_text(encoding="utf-8"))
    del sig["signature"]
    bad_sig = WORKDIR / "bad_signature.sig"
    bad_sig.write_text(json.dumps(sig), encoding="utf-8")
    return bad_sig


def case_10_derived_evidence_without_declared_omission(d: Path) -> None:
    # Toda la evidencia sigue siendo verification_status=derived, pero se
    # retira EVIDENCE_NOT_VERIFIED de manifest.omissions -- omision faltante.
    rewrite_json(
        d / "manifest.json",
        lambda m: m.__setitem__("omissions", [o for o in m["omissions"] if o["code"] != "EVIDENCE_NOT_VERIFIED"]),
    )


def case_11_partial_chain_breaks_logical_id(d: Path) -> None:
    # Se cambia el logical_id de la version vigente del reglamento, de modo
    # que su supersedes_source_id (la version 2025) ya NO comparte
    # logical_id -- cadena de version rota (independientemente de que el
    # historial completo este o no presente en el paquete).
    def mutate(recs: list[dict]) -> None:
        for i, s in enumerate(recs):
            if s.get("supersedes_source_id"):
                recs[i] = {**s, "logical_id": "urn:nexom:source-logical:00000000-0000-0000-0000-000000000000"}
                break
    rewrite_jsonl(d / "sources.jsonl", mutate)


def case_12_metadata_references_local_code(d: Path) -> None:
    # inherited_metadata usa el codigo local ("campus") como clave en vez
    # del field_definition_id portable -- debe rechazarse a nivel de schema
    # (chunk.schema.json exige propertyNames con patron urn:nexom:field:...).
    def mutate(recs: list[dict]) -> None:
        for i, c in enumerate(recs):
            if c.get("inherited_metadata"):
                recs[i] = {**c, "inherited_metadata": {"campus": "LEON"}}
                break
    rewrite_jsonl(d / "chunks.jsonl", mutate)


def case_13_missing_top_k(d: Path) -> None:
    def mutate(recs: list[dict]) -> None:
        rec = dict(recs[0])
        del rec["top_k"]
        recs[0] = rec
    rewrite_jsonl(d / "acceptance_cases.jsonl", mutate)


# ---------------------------------------------------------------------------
# Casos negativos 14-18 (rc3.1): las 2 brechas confirmadas por la auditoria
# independiente del cuarto veredicto, mas 3 casos adicionales pedidos
# explicitamente (chunk con texto manipulado, ZIP con path traversal).
# ---------------------------------------------------------------------------

def case_14_source_id_no_determinista(d: Path) -> None:
    """source.id sustituido por un UUID arbitrario, propagado de forma
    INTERNAMENTE consistente a chunks/evidence/media/source_metadata/
    acceptance_cases -- el unico defecto es que `id` ya no es igual a
    portable_source_id(lineage_id, version_key). Antes de la correccion
    rc3.1 esto pasaba con 0 errores (confirmado por auditoria)."""
    sources = load_jsonl(d, "sources.jsonl")
    chunks = load_jsonl(d, "chunks.jsonl")
    evidence = load_jsonl(d, "evidence.jsonl")
    media = load_jsonl(d, "media.jsonl")
    source_metadata = load_jsonl(d, "source_metadata.jsonl")
    acceptance_cases = load_jsonl(d, "acceptance_cases.jsonl")

    # La fuente sin relaciones de supersesion (para aislar del caso 11).
    target = next(s for s in sources if s["title"] == "Catalogo de Programas Academicos")
    old_id = target["id"]
    new_id = "urn:nexom:source:11111111-2222-3333-4444-555555555555"
    target["id"] = new_id

    chunk_id_map: dict[str, str] = {}
    for c in chunks:
        if c["source_id"] == old_id:
            old_cid = c["id"]
            c["source_id"] = new_id
            new_cid = k.portable_chunk_id(new_id, c["chunk_index"], c["text"])
            chunk_id_map[old_cid] = new_cid
            c["id"] = new_cid
    for c in chunks:
        for link in ("previous_chunk_id", "next_chunk_id", "parent_chunk_id"):
            if c.get(link) in chunk_id_map:
                c[link] = chunk_id_map[c[link]]

    evidence_id_map: dict[str, str] = {}
    for e in evidence:
        if e["source_id"] == old_id:
            old_eid = e["id"]
            e["source_id"] = new_id
            e["chunk_id"] = chunk_id_map.get(e["chunk_id"], e["chunk_id"])
            new_eid = k.portable_evidence_id(e["chunk_id"], e["evidence_kind"])
            evidence_id_map[old_eid] = new_eid
            e["id"] = new_eid

    for m in media:
        if m["source_id"] == old_id:
            m["source_id"] = new_id
            m["chunk_id"] = chunk_id_map.get(m["chunk_id"], m["chunk_id"])
            m["id"] = k.portable_media_id(m["chunk_id"], m["checksum"])

    for sm in source_metadata:
        if sm["source_id"] == old_id:
            sm["source_id"] = new_id
            sm["id"] = f"{new_id}:{sm['field_definition_id']}"

    for case in acceptance_cases:
        case["expected_source_ids"] = [new_id if s == old_id else s for s in case["expected_source_ids"]]
        case["expected_chunk_ids"] = [chunk_id_map.get(c, c) for c in case["expected_chunk_ids"]]
        case["expected_evidence_ids"] = [evidence_id_map.get(e, e) for e in case["expected_evidence_ids"]]

    save_jsonl(d, "sources.jsonl", sources)
    save_jsonl(d, "chunks.jsonl", chunks)
    save_jsonl(d, "evidence.jsonl", evidence)
    save_jsonl(d, "media.jsonl", media)
    save_jsonl(d, "source_metadata.jsonl", source_metadata)
    save_jsonl(d, "acceptance_cases.jsonl", acceptance_cases, sort_key="case_id")
    recompute_checksums(d)


def case_15_must_not_retrieve_inexistente(d: Path) -> None:
    """must_not_retrieve apunta a un id que no existe en el paquete --
    permite que una prueba de denegacion "apruebe vacio"."""
    def mutate(recs: list[dict]) -> None:
        recs[0] = {**recs[0], "must_not_retrieve": ["urn:nexom:source:00000000-0000-0000-0000-000000000000"]}
    rewrite_jsonl(d / "acceptance_cases.jsonl", mutate)
    recompute_checksums(d)


def case_16_chunk_esperado_sobre_nivel_acceso(d: Path) -> None:
    """expected_chunk_ids referencia un chunk de una fuente confidencial,
    con expected_source_ids vacio (para evadir el chequeo que SI existia en
    rc3) y user_access_level=publico -- caso mal formado que antes de rc3.1
    pasaba con 0 errores."""
    sources = load_jsonl(d, "sources.jsonl")
    chunks = load_jsonl(d, "chunks.jsonl")
    conf_source = next(s for s in sources if s["access_level"] == "confidencial")
    conf_chunk = next(c for c in chunks if c["source_id"] == conf_source["id"])

    def mutate(recs: list[dict]) -> None:
        recs[0] = {
            **recs[0],
            "expected_source_ids": [],
            "expected_chunk_ids": [conf_chunk["id"]],
            "user_access_level": "publico",
        }
    rewrite_jsonl(d / "acceptance_cases.jsonl", mutate)
    recompute_checksums(d)


def case_17_chunk_texto_manipulado(d: Path) -> None:
    """El texto de un chunk se altera DESPUES de haber calculado su id --
    el fingerprint recomputado ya no coincide (verificado por
    validate_lineage_continuity, pero sin caso explicito en la suite hasta
    ahora)."""
    def mutate(recs: list[dict]) -> None:
        recs[0] = {**recs[0], "text": recs[0]["text"] + " [contenido alterado tras generar el id]"}
    rewrite_jsonl(d / "chunks.jsonl", mutate)
    recompute_checksums(d)


def case_18_zip_path_traversal(_: Path) -> Path:
    """ZIP con una entrada que intenta escapar del directorio de extraccion
    (`../../etc/evil.txt`) -- debe rechazarse en la primera pasada de
    seguridad, antes de leer manifest.json siquiera."""
    zpath = WORKDIR / "case_18_traversal.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for f in BASE_PKG.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(BASE_PKG))
        zf.writestr("../../etc/evil.txt", "contenido malicioso")
    return zpath


def case_19_evidence_source_id_no_coincide_con_chunk(d: Path) -> None:
    """evidence.chunk_id sigue apuntando a un chunk de una fuente
    `confidencial`, pero evidence.source_id se falsea a una fuente
    `publica` -- y un acceptance_case de usuario publico espera esa
    evidencia. Antes de la correccion rc3.2, `source_for_evidence()`
    resolvia via `evidence.source_id` (el campo falseado) en vez de via
    `evidence.chunk_id`, y el caso pasaba con 0 errores."""
    sources = load_jsonl(d, "sources.jsonl")
    chunks = load_jsonl(d, "chunks.jsonl")
    evidence = load_jsonl(d, "evidence.jsonl")
    acceptance_cases = load_jsonl(d, "acceptance_cases.jsonl")

    conf_source = next(s for s in sources if s["access_level"] == "confidencial")
    conf_chunk = next(c for c in chunks if c["source_id"] == conf_source["id"])
    pub_source = next(s for s in sources if s["access_level"] == "publico")
    target_evidence = next(e for e in evidence if e["chunk_id"] == conf_chunk["id"])
    target_evidence["source_id"] = pub_source["id"]

    for case in acceptance_cases:
        if case["case_id"] == "AC-001-requisitos-admision":
            case["expected_evidence_ids"] = [target_evidence["id"]]
            case["expected_chunk_ids"] = []
            case["expected_source_ids"] = []
            case["user_access_level"] = "publico"

    save_jsonl(d, "evidence.jsonl", evidence)
    save_jsonl(d, "acceptance_cases.jsonl", acceptance_cases, sort_key="case_id")
    recompute_checksums(d)


NEGATIVE_CASES = [
    ("01_invalid_date", case_01_invalid_date, "dir"),
    ("02_omission_reason_null_falso", case_02_false_omission_reason_null, "dir"),
    ("03_media_incluida_sin_binario", case_03_false_media_included_without_binary, "dir"),
    ("04_conteo_manifest_falso", case_04_false_manifest_count, "dir"),
    ("05_activo_declarado_ausente", case_05_declared_but_absent_asset, "dir"),
    ("06_activo_sin_checksum", case_06_asset_present_without_checksum, "dir"),
    ("07_archivo_extra_no_declarado", case_07_extra_file_in_directory, "dir"),
    ("08_entrada_duplicada_en_zip", case_08_duplicate_entry_inside_zip, "zip"),
    ("09_sidecar_no_cumple_schema", case_09_sidecar_not_conforming_to_schema, "sidecar"),
    ("10_evidencia_derivada_sin_omision", case_10_derived_evidence_without_declared_omission, "dir"),
    ("11_cadena_logical_id_rota", case_11_partial_chain_breaks_logical_id, "dir"),
    ("12_metadata_referencia_codigo_local", case_12_metadata_references_local_code, "dir"),
    ("13_falta_top_k_en_acceptance_case", case_13_missing_top_k, "dir"),
    ("14_source_id_no_determinista", case_14_source_id_no_determinista, "dir"),
    ("15_must_not_retrieve_inexistente", case_15_must_not_retrieve_inexistente, "dir"),
    ("16_chunk_esperado_sobre_nivel_acceso", case_16_chunk_esperado_sobre_nivel_acceso, "dir"),
    ("17_chunk_texto_manipulado", case_17_chunk_texto_manipulado, "dir"),
    ("18_zip_path_traversal", case_18_zip_path_traversal, "zip"),
    ("19_evidence_source_id_no_coincide_con_chunk", case_19_evidence_source_id_no_coincide_con_chunk, "dir"),
]


def main() -> int:
    if not BASE_PKG.exists():
        print(f"ERROR: no existe {BASE_PKG} -- correr generate_example.py primero", file=sys.stderr)
        return 1
    WORKDIR.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []

    # --- N casos negativos (ver NEGATIVE_CASES): cada uno DEBE ser rechazado (exit 1) ---
    for name, case_fn, kind in NEGATIVE_CASES:
        if kind == "dir":
            pkg = fresh_copy(name)
            case_fn(pkg)
            code, out = run_validator(pkg)
        elif kind == "zip":
            zpath = case_fn(BASE_PKG)
            code, out = run_validator(zpath)
        elif kind == "sidecar":
            bad_sig = case_fn(BASE_PKG)
            code, out = run_validator(
                BASE_PKG,
                [
                    "--content-digest-file", str(CONTENT_DIGEST_FILE),
                    "--signature-file", str(bad_sig),
                    "--public-key", str(PUBLIC_KEY_FILE),
                ],
            )
        else:  # pragma: no cover
            raise AssertionError(kind)

        rejected = code == 1
        status = "PASS (rechazado correctamente)" if rejected else "FAIL -- fue ACEPTADO (deberia rechazarse)"
        print(f"[{name}] {status}")
        if not rejected:
            failures.append(name)
            print(out)

    # --- caso base: el paquete SIN mutar debe seguir siendo aceptado ---
    code, out = run_validator(
        BASE_PKG,
        [
            "--content-digest-file", str(CONTENT_DIGEST_FILE),
            "--signature-file", str(SIGNATURE_FILE),
            "--public-key", str(PUBLIC_KEY_FILE),
        ],
    )
    accepted = code == 0
    status = "PASS (aceptado correctamente)" if accepted else "FAIL -- el paquete BASE valido fue RECHAZADO"
    print(f"[00_baseline_valido] {status}")
    if not accepted:
        failures.append("00_baseline_valido")
        print(out)

    print()
    total = len(NEGATIVE_CASES) + 1
    print(f"RESUMEN: {total - len(failures)}/{total} casos correctos")
    if failures:
        print(f"CASOS FALLIDOS: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
