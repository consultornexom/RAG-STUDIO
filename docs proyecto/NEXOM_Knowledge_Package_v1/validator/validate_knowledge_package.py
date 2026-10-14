#!/usr/bin/env python3
"""Validador de referencia -- NEXOM Knowledge Package v1.0-rc3.2 (RAG-INC-00).

rc3.2 cierra un tercer hueco confirmado por auditoria independiente sobre
rc3.1 (checksums.json recalculado tras la mutacion, mismo metodo de
aislamiento que en rondas anteriores):
  (g) `evidence.jsonl` declara `source_id` como copia informativa, pero
      `validate_acceptance_semantics` resolvia la fuente de una evidencia
      esperada leyendo ESE campo directamente, en vez de resolverla via
      `evidence.chunk_id -> chunk.source_id` (la relacion real). Una
      evidencia cuyo `chunk_id` seguia apuntando a un chunk de una fuente
      `confidencial`, pero con `source_id` falseado a una fuente `publica`,
      pasaba la verificacion de jerarquia de acceso con 0 errores.
  Ver [rc3.2] en el codigo. Corregido en dos capas independientes:
  `source_for_evidence()` ahora resuelve SIEMPRE via `chunk_id`, y
  `validate_referential_integrity` rechaza por separado cualquier
  `evidence.source_id` que no coincida con el `source_id` real de su
  `chunk_id` (para que la inconsistencia en si misma sea un error, no solo
  un efecto que la resolucion correcta esconde).

rc3.1 fue un PARCHE DE ALINEACION sobre rc3, no un rediseno: la auditoria
independiente del cuarto veredicto NEXOM reprodujo, con aislamiento
controlado (checksums.json recalculado para que el unico defecto probado
fuera el que se afirmaba), dos huecos reales que rc3 dejaba pasar con
0 errores:
  (e) `source.id` (identidad de VERSION) sustituido por un UUID arbitrario,
      propagado de forma consistente a chunks/evidence/media/acceptance_cases
      -- nada recomputaba `portable_source_id(lineage_id, version_key)`.
  (f) `acceptance_cases.jsonl` con `must_not_retrieve` apuntando a un id
      inexistente, o con `expected_chunk_ids`/`expected_evidence_ids` de
      una fuente por encima del `user_access_level` de la propia prueba
      (con `expected_source_ids` vacio para evitarlo) -- solo se validaba
      `expected_source_ids`, no las otras tres listas.
  Ver [rc3.1] en el codigo para las correcciones puntuales.

rc3 fue a su vez una ronda de ALINEACION, no de rediseno: el tercer
veredicto NEXOM demostro con 4 casos concretos que el validador rc2
aceptaba en silencio (0 errores de schema) violaciones que el ADR afirma
prohibir:
  (a) created_at="not-a-date"
  (b) original_included=false con original_omission_reason=null
  (c) media.included_in_package=true sin que el binario exista realmente
  (d) manifest.counts.chunks=999 cuando el paquete tiene 6

Las 8 correcciones bloqueantes de rc3, cada una localizable por su
etiqueta [correccion-N] en el codigo:

  [correccion-1] FormatChecker real (rfc3339-validator) + autochequeo de
                 arranque: exactamente 14 schemas, todos check_schema() OK.
  [correccion-2] Reglas de perfil/originales cruzadas contra manifest.profile
                 + limite de tamano DEFINITIVO para originales incluidos
                 (50 MB, ya no "a confirmar").
  [correccion-3] Igualdad de conjuntos EXACTA entre archivos fisicos,
                 manifest.files, checksums.files+checksums.json y activos
                 declarados (media/original) -- faltantes, sobrantes,
                 duplicados, binarios ausentes, checksums incompletos,
                 conteos falsos. En modo zip, ademas: entradas duplicadas
                 y entradas cifradas.
  [correccion-4] Ya NO se recomputa `logical_id` (es opaco por diseno) --
                 se verifica CONTINUIDAD DE CADENA: mismo logical_id en
                 toda supersesion presente en el paquete.
  [correccion-5] `field_definition_id` (URN) es la clave relacional real en
                 source_metadata.jsonl y Chunk.inherited_metadata -- se
                 verifica que exista en metadata_schema.fields[].id.
  [correccion-6] El sidecar `.sig` se valida contra signature.schema.json
                 ANTES de usar sus campos. `--trusted-key-id` es opcional y
                 documenta que Agent Runtime en produccion debe mantener su
                 propio almacen de confianza -- ninguna clave publica
                 entregada por linea de comandos prueba identidad por si
                 sola.
  [correccion-7] capabilities/omissions se valida BIDIRECCIONALMENTE para
                 los 4 codigos definidos, incluida la deteccion de
                 omisiones declaradas falsamente.
  [correccion-8] Semantica ejecutable de acceptance_cases.jsonl:
                 top_k/match_policy/minimum_recall (ya exigidos por schema)
                 mas verificacion cruzada contra access_hierarchy.json (un
                 caso no puede esperar recuperar una fuente por encima del
                 nivel de acceso del usuario de la prueba).

Endurecimientos no bloqueantes incluidos: sidecar renombrado
`.content.sha256`, `content_digest` via estructura JSON canonica (ya en
id_scheme.py), errores controlados en vez de tracebacks, dependencias
fijadas en requirements.lock.txt.

Dependencias externas: `jsonschema`, `rfc3339-validator`, `rfc8785`,
`cryptography` -- ver requirements.lock.txt para versiones exactas.

Uso:
    python3 validate_knowledge_package.py <directorio_o_zip> \\
        [--content-digest-file paquete.content.sha256] \\
        [--signature-file paquete.sig] \\
        [--public-key clave.pem] \\
        [--trusted-key-id key-id-esperado] \\
        [--zip-sha256-file paquete.zip.sha256]

Codigo de salida: 0 si todo valido, 1 si hay al menos un error (incluidos
errores de entrada malformada -- nunca una traceback sin controlar).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
import id_scheme as k  # noqa: E402

from jsonschema import Draft202012Validator  # noqa: E402
from jsonschema.exceptions import SchemaError  # noqa: E402

try:
    import rfc3339_validator  # noqa: F401
    _HAVE_RFC3339 = True
except ImportError:
    _HAVE_RFC3339 = False

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
EXPECTED_SCHEMA_COUNT = 14

JSONL_FILES = {
    "sources.jsonl": "source.schema.json",
    "chunks.jsonl": "chunk.schema.json",
    "source_metadata.jsonl": "source_metadata.schema.json",
    "evidence.jsonl": "evidence.schema.json",
    "media.jsonl": "media.schema.json",
    "acceptance_cases.jsonl": "acceptance_case.schema.json",
}
JSON_FILES = {
    "manifest.json": "manifest.schema.json",
    "metadata_schema.json": "metadata_schema.schema.json",
    "conversational_bundle.json": "conversational_bundle.schema.json",
    "embedding_spaces.json": "embedding_spaces.schema.json",
    "indexes.json": "indexes.schema.json",
    "checksums.json": "checksums.schema.json",
    "access_hierarchy.json": "access_hierarchy.schema.json",
}
FORBIDDEN_INSIDE_PACKAGE = {"signature.json"}
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
ORIGINAL_SIZE_LIMIT_BYTES = 50 * 1024 * 1024  # [correccion-2] limite DEFINITIVO v1.0, ya no "a confirmar"
VALID_ORIGINAL_OMISSION_REASONS_BY_PROFILE = {
    "CORE": {"not_applicable_profile_core"},
    "AUDIT": {"license", "confidential", "size_limit", "no_binary_source", "other"},
    "PREINDEXED": set(),  # [correccion-2] PREINDEXED no esta implementado en v1.0
}


class ValidationAborted(Exception):
    """Error de entrada irrecuperable (JSON malformado, falta un archivo
    requerido para continuar, etc.) -- se atrapa en main() y se reporta
    como error controlado, nunca como traceback sin manejar."""


class Report:
    def __init__(self) -> None:
        self.ok: list[str] = []
        self.errors: list[str] = []

    def check(self, condition: bool, ok_msg: str, err_msg: str) -> bool:
        (self.ok if condition else self.errors).append(ok_msg if condition else err_msg)
        return condition

    def error(self, msg: str) -> None:
        self.errors.append(msg)


def load_schema(name: str) -> dict:
    try:
        return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationAborted(f"no se pudo cargar el schema {name}: {exc}") from exc


def make_validator(schema: dict) -> Draft202012Validator:
    # [correccion-1] format_checker SIEMPRE explicito. Sin esto, y sin
    # rfc3339-validator instalado, jsonschema NO valida format="date-time"
    # (es un no-op silencioso) -- exactamente el hallazgo del 3er veredicto.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def selfcheck_schemas(report: Report) -> None:
    """[correccion-1] Autochequeo de arranque, reproducible por cualquiera:
    deben existir EXACTAMENTE 14 archivos *.schema.json y todos deben pasar
    check_schema(). Se ejecuta ANTES de validar ningun paquete."""
    if not _HAVE_RFC3339:
        raise ValidationAborted(
            "falta la dependencia 'rfc3339-validator' -- sin ella, jsonschema NO "
            "valida format=\"date-time\" aunque se pase format_checker (es un "
            "no-op silencioso). Instalar con: pip install -r requirements.lock.txt"
        )
    found = sorted(SCHEMAS_DIR.glob("*.schema.json"))
    report.check(
        len(found) == EXPECTED_SCHEMA_COUNT,
        f"[autochequeo] {len(found)} schemas encontrados en {SCHEMAS_DIR.name}/ (esperados {EXPECTED_SCHEMA_COUNT})",
        f"[autochequeo] {len(found)} schemas encontrados en {SCHEMAS_DIR.name}/ -- esperados {EXPECTED_SCHEMA_COUNT}: {[f.name for f in found]}",
    )
    for f in found:
        try:
            schema = json.loads(f.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            report.ok.append(f"[autochequeo] {f.name} es un JSON Schema draft 2020-12 valido")
        except (json.JSONDecodeError, SchemaError) as exc:
            report.error(f"[autochequeo] {f.name} NO es un schema valido: {exc}")


def _path_is_safe(name: str) -> bool:
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return False
    if ".." in Path(name).parts:
        return False
    return True


def safe_extract_zip(zip_path: Path, dest: Path, report: Report) -> bool:
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        report.error(f"[seguridad-zip] archivo .zip malformado o corrupto: {exc}")
        return False

    with zf:
        # Pasada 1: seguridad de rutas/symlinks/tamanos/duplicados/cifrado
        # sobre TODAS las entradas, sin extraer y sin confiar todavia en
        # manifest.json.
        seen_names: set[str] = set()
        total = 0
        for info in zf.infolist():
            if info.filename in seen_names:
                report.error(f"[seguridad-zip][correccion-3] entrada duplicada dentro del zip: {info.filename}")
                return False
            seen_names.add(info.filename)
            if info.flag_bits & 0x1:
                report.error(f"[seguridad-zip][correccion-3] entrada cifrada rechazada (no soportado): {info.filename}")
                return False
            if not _path_is_safe(info.filename):
                report.error(f"[seguridad-zip] ruta insegura rechazada: {info.filename}")
                return False
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                report.error(f"[seguridad-zip] symlink rechazado: {info.filename}")
                return False
            if info.file_size > MAX_FILE_BYTES:
                report.error(f"[seguridad-zip] archivo excede el limite individual: {info.filename}")
                return False
            total += info.file_size
        if total > MAX_TOTAL_BYTES:
            report.error("[seguridad-zip] tamano total descomprimido excede el limite")
            return False

        # Pasada 2: leer manifest.json DIRECTO del zip (sin extraer nada
        # mas) para construir el allowlist real del contrato.
        if "manifest.json" not in zf.namelist():
            report.error("[seguridad-zip] falta manifest.json -- no se puede construir el allowlist, se rechaza el paquete")
            return False
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except json.JSONDecodeError as exc:
            report.error(f"[seguridad-zip] manifest.json dentro del zip es JSON invalido: {exc}")
            return False
        allowed = set(manifest.get("files", []))
        try:
            media_records = [json.loads(line) for line in zf.read("media.jsonl").decode("utf-8").splitlines() if line.strip()]
            for m in media_records:
                if m.get("included_in_package"):
                    allowed.add(m["relative_path"])
        except KeyError:
            pass
        try:
            src_records = [json.loads(line) for line in zf.read("sources.jsonl").decode("utf-8").splitlines() if line.strip()]
            for s in src_records:
                if s.get("original_included") and s.get("original_relative_path"):
                    allowed.add(s["original_relative_path"])
        except KeyError:
            pass

        # Pasada 3: cada entrada del zip debe pertenecer al allowlist
        # derivado del propio manifest, y nada prohibido (signature.json)
        # puede viajar dentro.
        for name in zf.namelist():
            if name in FORBIDDEN_INSIDE_PACKAGE:
                report.error(f"[seguridad-zip] {name} no debe viajar dentro del paquete (debe ser sidecar externo, ver ADR seccion 3)")
                return False
            if name not in allowed:
                report.error(f"[seguridad-zip][correccion-3] archivo no declarado en manifest.files ni en activos declarados: {name}")
                return False

        report.ok.append(
            f"[seguridad-zip] {len(zf.namelist())} entradas dentro del allowlist derivado de manifest.json; "
            f"sin rutas inseguras, symlinks, duplicados, entradas cifradas, excesos de tamano, ni signature.json embebido"
        )
        zf.extractall(dest)
    return True


def read_jsonl(path: Path) -> list[dict]:
    records = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationAborted(f"no se pudo leer {path.name}: {exc}") from exc
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValidationAborted(f"{path.name} linea {i + 1}: JSON invalido ({exc})") from exc
    return records


def validate_schemas(pkg_dir: Path, report: Report) -> dict:
    data: dict[str, object] = {}

    for extra in FORBIDDEN_INSIDE_PACKAGE:
        if (pkg_dir / extra).exists():
            report.error(f"[schema] {extra} encontrado DENTRO del paquete -- prohibido, debe ser sidecar externo")

    for fname, schema_name in JSON_FILES.items():
        fpath = pkg_dir / fname
        if not fpath.exists():
            report.error(f"[schema] falta archivo requerido: {fname}")
            continue
        try:
            obj = json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.error(f"[schema] {fname} es JSON invalido: {exc}")
            continue
        validator = make_validator(load_schema(schema_name))
        errs = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
        if errs:
            for e in errs:
                report.error(f"[schema] {fname}: {'/'.join(str(p) for p in e.path)}: {e.message}")
        else:
            report.ok.append(f"[schema] {fname} cumple {schema_name}")
        data[fname] = obj

    for fname, schema_name in JSONL_FILES.items():
        fpath = pkg_dir / fname
        if not fpath.exists():
            report.error(f"[schema] falta archivo requerido: {fname}")
            continue
        records = read_jsonl(fpath)
        validator = make_validator(load_schema(schema_name))
        bad = 0
        for idx, rec in enumerate(records):
            errs = list(validator.iter_errors(rec))
            if errs:
                bad += 1
                for e in errs[:3]:
                    report.error(f"[schema] {fname} registro {idx}: {'/'.join(str(p) for p in e.path)}: {e.message}")
        if bad == 0:
            report.ok.append(f"[schema] {fname} ({len(records)} registros) cumple {schema_name}")
        data[fname] = records

    return data


def validate_referential_integrity(data: dict, report: Report) -> None:
    sources = {s["id"]: s for s in data.get("sources.jsonl", [])}
    chunks = {c["id"]: c for c in data.get("chunks.jsonl", [])}
    meta_schema = data.get("metadata_schema.json", {}) or {}
    fields_by_id = {f["id"]: f for f in meta_schema.get("fields", [])}
    catalogs = {c["id"]: c for c in meta_schema.get("catalogs", [])}
    bundle = data.get("conversational_bundle.json", {}) or {}
    variables = {v["id"] for v in bundle.get("conversational_variables", [])}
    channelings = {c["id"] for c in bundle.get("channeling_schemes", [])}
    espaces = {e["id"] for e in data.get("embedding_spaces.json", [])}

    def ref(condition, label):
        report.check(condition, f"[referencial] {label} OK", f"[referencial] {label} FALLA")

    for c in chunks.values():
        ref(c["source_id"] in sources, f"chunk {c['id']} -> source_id existente")
        for link in ("previous_chunk_id", "next_chunk_id", "parent_chunk_id"):
            v = c.get(link)
            ref(v is None or v in chunks, f"chunk {c['id']} -> {link} existente")
        # [correccion-5] las claves de inherited_metadata deben ser
        # field_definition_id (URN) que existan realmente en metadata_schema.
        for field_definition_id in c.get("inherited_metadata", {}):
            ref(
                field_definition_id in fields_by_id,
                f"chunk {c['id']} inherited_metadata clave {field_definition_id} -> FieldDefinition existente en metadata_schema.json",
            )

    for e in data.get("evidence.jsonl", []):
        ref(e["source_id"] in sources, f"evidence {e['id']} -> source_id existente")
        ref(e["chunk_id"] in chunks, f"evidence {e['id']} -> chunk_id existente")
        # [rc3.2] evidence.source_id DEBE coincidir con la fuente real del
        # chunk que referencia (chunk.source_id) -- de lo contrario una
        # evidencia puede declarar un source_id publico mientras su
        # chunk_id sigue apuntando a un chunk de una fuente confidencial,
        # eludiendo la verificacion de acceso en validate_acceptance_semantics
        # (que ademas ahora resuelve SIEMPRE via chunk_id, no via este campo
        # directamente -- este chequeo detecta la inconsistencia en si).
        if e["chunk_id"] in chunks:
            owner_source_id = chunks[e["chunk_id"]]["source_id"]
            ref(
                e["source_id"] == owner_source_id,
                f"evidence {e['id']} -> source_id coincide con la fuente real de su chunk_id ({owner_source_id})",
            )

    for m in data.get("media.jsonl", []):
        ref(m["chunk_id"] in chunks, f"media {m['id']} -> chunk_id existente")
        ref(m["source_id"] in sources, f"media {m['id']} -> source_id existente")

    for sm in data.get("source_metadata.jsonl", []):
        ref(sm["source_id"] in sources, f"source_metadata {sm['id']} -> source_id existente")
        # [correccion-5] field_definition_id es la clave relacional real
        # (rc2 usaba erroneamente el codigo local field_id como si fuera FK).
        fdef = fields_by_id.get(sm["field_definition_id"])
        ref(fdef is not None, f"source_metadata {sm['id']} -> field_definition_id {sm['field_definition_id']} declarado en metadata_schema.json")
        if fdef:
            ref(
                fdef.get("field_id") == sm.get("field_code"),
                f"source_metadata {sm['id']} field_code '{sm.get('field_code')}' coincide con FieldDefinition.field_id '{fdef.get('field_id')}' (informativo, no es la clave real)",
            )
            if fdef.get("catalog_id"):
                cat = catalogs.get(fdef["catalog_id"])
                ref(cat is not None, f"campo {sm['field_definition_id']} -> catalog_id existente")
                if cat:
                    valid_codes = {en["value_code"] for en in cat["entries"]}
                    for code in sm["value"]:
                        ref(code in valid_codes, f"source_metadata {sm['id']} valor '{code}' existe en catalogo '{cat['name']}'")

    for f in fields_by_id.values():
        if f.get("catalog_id"):
            ref(f["catalog_id"] in catalogs, f"field {f['id']} -> catalog_id existente")
    for cat in catalogs.values():
        codes = {en["value_code"] for en in cat["entries"]}
        for en in cat["entries"]:
            ref(en["parent_entry_code"] is None or en["parent_entry_code"] in codes,
                f"catalog {cat['name']} entry {en['value_code']} -> parent_entry_code existente")

    for intent in bundle.get("intents", []):
        for v in intent.get("required_variables", []) + intent.get("optional_variables", []):
            ref(v in variables, f"intent {intent['name']} -> variable {v} declarada")
        fb = intent.get("fallback_channeling_code")
        ref(fb is None or fb in channelings, f"intent {intent['name']} -> fallback_channeling_code declarado")

    for idx in data.get("indexes.json", []):
        ref(idx["embedding_space_id"] in espaces, f"index {idx['id']} -> embedding_space_id declarado")


def validate_lineage_continuity(data: dict, report: Report) -> None:
    """[correccion-4] `logical_id` es OPACO -- ya NO se recomputa. Solo se
    verifica CONTINUIDAD: si una fuente supersede a otra presente en el
    mismo paquete, ambas deben compartir logical_id. Tambien se recomputa
    `chunk_fingerprint` (si es determinista) y `source.id` (version id,
    si es determinista a partir de logical_id+contenido)."""
    manifest = data.get("manifest.json", {}) or {}
    kb_id = manifest.get("knowledge_base_id", "")
    report.check(
        k.is_valid_knowledge_base_id(kb_id),
        f"[ids] manifest.knowledge_base_id ({kb_id}) tiene forma de UUID valido",
        f"[ids] manifest.knowledge_base_id ({kb_id}) NO tiene forma de UUID valido",
    )

    sources = data.get("sources.jsonl", [])
    by_id = {s["id"]: s for s in sources}

    for s in sources:
        report.check(
            s["id"].startswith("urn:nexom:source:") and s["logical_id"].startswith("urn:nexom:source-logical:"),
            f"[ids] source {s['id']} logical_id tiene forma URN valida (opaco, no se recomputa)",
            f"[ids] source {s['id']} logical_id ({s.get('logical_id')}) no tiene forma URN valida",
        )
        if s.get("supersedes_source_id"):
            parent = by_id.get(s["supersedes_source_id"])
            report.check(
                parent is not None and parent["logical_id"] == s["logical_id"],
                f"[ids][correccion-4] source {s['id']} supersedes_source_id comparte logical_id con su version anterior (continuidad de cadena)",
                f"[ids][correccion-4] source {s['id']} supersedes_source_id NO comparte logical_id -- cadena de version rota",
            )

        # [rc3.1] `source.id` (identidad de VERSION) SI es determinista --
        # a diferencia de `logical_id` (opaco), se calcula a partir de
        # lineage_id + version_key y DEBE recomputarse y compararse. Esto
        # cerraba un hueco real en rc3: nada verificaba que `id` cumpliera
        # realmente la formula documentada en id_scheme.py/ADR seccion 2 --
        # un id arbitrario, propagado de forma consistente a todos sus
        # dependientes, pasaba con 0 errores.
        logical_prefix = "urn:nexom:source-logical:"
        if s.get("logical_id", "").startswith(logical_prefix):
            lineage_id = s["logical_id"][len(logical_prefix):]
            version_key = k.source_version_key(
                s.get("content_hash"), s.get("title", ""), s.get("source_type", ""), s.get("updated_at", "")
            )
            expected_id = k.portable_source_id(lineage_id, version_key)
            report.check(
                expected_id == s["id"],
                f"[ids][rc3.1] source {s['id']} id de version recomputado coincide (portable_source_id(lineage_id, version_key))",
                f"[ids][rc3.1] source {s['id']} id de version NO coincide con la formula del contrato -- recomputado {expected_id} "
                f"(lineage_id={lineage_id}, version_key derivado de content_hash/title/source_type/updated_at)",
            )

    for c in data.get("chunks.jsonl", []):
        expected = k.portable_chunk_id(c["source_id"], c["chunk_index"], c["text"])
        report.check(
            expected == c["id"],
            f"[ids] chunk {c['id']} recomputado coincide",
            f"[ids] chunk {c['id']} NO coincide con recomputo ({expected}) -- texto o indice alterado tras generar el id",
        )


def validate_file_set_and_counts(pkg_dir: Path, data: dict, report: Report) -> None:
    """[correccion-3] Igualdad EXACTA de conjuntos entre lo fisicamente
    presente, manifest.files, checksums.files+checksums.json y los activos
    declarados por media.jsonl/sources.jsonl -- mas verificacion de
    manifest.counts contra los registros realmente cargados."""
    manifest = data.get("manifest.json", {}) or {}
    checksums = data.get("checksums.json", {}) or {}

    manifest_files = set(manifest.get("files", []))
    checksums_files = set(checksums.get("files", {}).keys()) | {"checksums.json"}
    report.check(
        manifest_files == checksums_files,
        "[archivos] manifest.files == checksums.files + {checksums.json}",
        f"[archivos] manifest.files DIFIERE de checksums.files+checksums.json -- "
        f"solo en manifest: {sorted(manifest_files - checksums_files)}, solo en checksums: {sorted(checksums_files - manifest_files)}",
    )

    on_disk = {
        str(p.relative_to(pkg_dir)).replace("\\", "/")
        for p in pkg_dir.rglob("*")
        if p.is_file()
    }
    missing = manifest_files - on_disk
    extra = on_disk - manifest_files
    report.check(
        not missing,
        "[archivos] todos los archivos de manifest.files estan presentes fisicamente",
        f"[archivos][correccion-3] archivos declarados en manifest.files pero AUSENTES del paquete: {sorted(missing)}",
    )
    report.check(
        not extra,
        "[archivos] no hay archivos fisicos fuera de manifest.files (sin sobrantes)",
        f"[archivos][correccion-3] archivos presentes en el paquete pero NO declarados en manifest.files: {sorted(extra)}",
    )

    # Activos declarados (media incluida / originales incluidos) deben
    # aparecer en manifest.files (si no, "declarado pero ausente" pasaria
    # desapercibido) y viceversa no se exige (un binario puede no
    # provenir de un unico registro).
    declared_media = {m["relative_path"] for m in data.get("media.jsonl", []) if m.get("included_in_package")}
    for rel in declared_media:
        report.check(
            rel in manifest_files,
            f"[archivos] media declarada incluida '{rel}' -> presente en manifest.files",
            f"[archivos][correccion-3] media.jsonl declara included_in_package=true para '{rel}' pero NO esta en manifest.files (binario declarado pero ausente)",
        )
        report.check(
            rel in on_disk,
            f"[archivos] media declarada incluida '{rel}' -> archivo fisico presente",
            f"[archivos][correccion-3] media.jsonl declara included_in_package=true para '{rel}' pero el archivo NO existe fisicamente en el paquete",
        )
        report.check(
            rel in checksums.get("files", {}),
            f"[archivos] media declarada incluida '{rel}' -> checksum presente en checksums.json",
            f"[archivos][correccion-3] media.jsonl declara included_in_package=true para '{rel}' pero checksums.json NO tiene su hash (checksum incompleto)",
        )

    declared_originals = {
        s["original_relative_path"] for s in data.get("sources.jsonl", []) if s.get("original_included") and s.get("original_relative_path")
    }
    for rel in declared_originals:
        report.check(
            rel in manifest_files and rel in on_disk,
            f"[archivos] original declarado '{rel}' -> presente en manifest.files y fisicamente",
            f"[archivos][correccion-3] source declara original_included=true con original_relative_path='{rel}' pero el archivo esta ausente de manifest.files y/o del paquete",
        )

    # [correccion-3] manifest.counts vs conteos reales recomputados desde
    # los propios registros cargados (nunca confiar en el numero declarado).
    bundle = data.get("conversational_bundle.json", {}) or {}
    actual_counts = {
        "sources": len(data.get("sources.jsonl", [])),
        "chunks": len(data.get("chunks.jsonl", [])),
        "evidence": len(data.get("evidence.jsonl", [])),
        "media": len(data.get("media.jsonl", [])),
        "intents": len(bundle.get("intents", [])),
        "guardrail_rules": len(bundle.get("guardrail_rules", [])),
        "acceptance_cases": len(data.get("acceptance_cases.jsonl", [])),
    }
    declared_counts = manifest.get("counts", {})
    for key, actual in actual_counts.items():
        declared = declared_counts.get(key)
        report.check(
            declared == actual,
            f"[conteos] manifest.counts.{key} = {declared} coincide con lo cargado del paquete",
            f"[conteos][correccion-3] manifest.counts.{key} declara {declared} pero el paquete contiene realmente {actual} registros",
        )


def validate_profile_and_originals(pkg_dir: Path, data: dict, report: Report) -> None:
    """[correccion-2] Cruce profile <-> original_included/original_omission_reason,
    y limite de tamano DEFINITIVO (50 MB) para originales incluidos."""
    manifest = data.get("manifest.json", {}) or {}
    profile = manifest.get("profile")
    valid_reasons = VALID_ORIGINAL_OMISSION_REASONS_BY_PROFILE.get(profile)
    report.check(
        profile in VALID_ORIGINAL_OMISSION_REASONS_BY_PROFILE,
        f"[perfil] manifest.profile = {profile} es un perfil reconocido por este validador",
        f"[perfil] manifest.profile = {profile} no es un perfil reconocido (CORE/AUDIT/PREINDEXED)",
    )
    if profile == "PREINDEXED":
        report.error("[perfil][correccion-2] perfil PREINDEXED no esta implementado en v1.0 -- ningun paquete debe declararlo todavia")

    for s in data.get("sources.jsonl", []):
        if profile == "CORE":
            report.check(
                s.get("original_included") is False,
                f"[perfil] source {s['id']}: original_included=false bajo perfil CORE",
                f"[perfil][correccion-2] source {s['id']}: original_included=true NO esta permitido bajo perfil CORE",
            )
        reason = s.get("original_omission_reason")
        if s.get("original_included") is False and valid_reasons is not None:
            report.check(
                reason in valid_reasons,
                f"[perfil] source {s['id']}: original_omission_reason='{reason}' es valido para perfil {profile}",
                f"[perfil][correccion-2] source {s['id']}: original_omission_reason='{reason}' NO es una razon valida bajo perfil {profile} (validas: {sorted(valid_reasons)})",
            )
        if s.get("original_included") is True and s.get("original_relative_path"):
            fpath = pkg_dir / s["original_relative_path"]
            if fpath.exists():
                size = fpath.stat().st_size
                report.check(
                    size <= ORIGINAL_SIZE_LIMIT_BYTES,
                    f"[perfil] original de {s['id']} ({size} bytes) esta dentro del limite de {ORIGINAL_SIZE_LIMIT_BYTES} bytes",
                    f"[perfil][correccion-2] original de {s['id']} ({size} bytes) EXCEDE el limite definitivo de {ORIGINAL_SIZE_LIMIT_BYTES} bytes (50 MB) -- debio omitirse con reason='size_limit'",
                )


def validate_capabilities_omissions(data: dict, report: Report) -> None:
    """[correccion-7] Validacion BIDIRECCIONAL para los 4 codigos de
    omission definidos -- si la condicion aplica y no se declaro, error;
    si se declaro pero la condicion NO aplica, tambien error (omision
    falsamente declarada)."""
    manifest = data.get("manifest.json", {}) or {}
    caps = manifest.get("capabilities", {})
    declared_codes = {o["code"] for o in manifest.get("omissions", [])}
    media = data.get("media.jsonl", [])
    evidence = data.get("evidence.jsonl", [])
    sources = data.get("sources.jsonl", [])
    indexes = data.get("indexes.json", [])
    profile = manifest.get("profile")

    def bidi(applies: bool, code: str, label: str) -> None:
        declared = code in declared_codes
        report.check(
            applies == declared,
            f"[omisiones][correccion-7] {code}: {'declarada' if declared else 'no declarada'} correctamente ({label})",
            f"[omisiones][correccion-7] {code}: {'declarada FALSAMENTE (la condicion no aplica)' if declared and not applies else 'FALTA declarar (la condicion aplica)'} ({label})",
        )

    # MEDIA_BINARIES_NOT_INCLUDED
    has_undelivered_media = any(not m.get("included_in_package") for m in media)
    bidi(has_undelivered_media, "MEDIA_BINARIES_NOT_INCLUDED", "existe al menos un media.jsonl con included_in_package=false")
    if has_undelivered_media:
        report.check(
            caps.get("image_retrieval") is False,
            "[capacidades] manifest.capabilities.image_retrieval=false cuando hay imagenes sin binario incluido",
            "[capacidades][correccion-7] manifest.capabilities.image_retrieval=true pero hay imagenes con included_in_package=false -- inconsistente",
        )

    # ORIGINALS_NOT_INCLUDED
    any_original_missing = any(not s.get("original_included") for s in sources) if sources else False
    bidi(any_original_missing, "ORIGINALS_NOT_INCLUDED", "existe al menos una fuente con original_included=false")

    # VECTORS_NOT_INCLUDED -- v1.0 nunca transporta vectores reales (CORE/AUDIT);
    # PREINDEXED no esta implementado (ver validate_profile_and_originals).
    vectors_missing = profile in ("CORE", "AUDIT")
    bidi(vectors_missing, "VECTORS_NOT_INCLUDED", f"perfil {profile} no transporta vectores en v1.0")

    # EVIDENCE_NOT_VERIFIED
    all_derived = bool(evidence) and all(e.get("verification_status") == "derived" for e in evidence)
    bidi(all_derived, "EVIDENCE_NOT_VERIFIED", "todos los registros de evidence.jsonl tienen verification_status=derived")

    # image_retrieval=true exige binarios completos + indice visual declarado.
    if caps.get("image_retrieval") is True:
        all_images_included = all(m.get("included_in_package") for m in media if m.get("media_type") == "image")
        report.check(
            all_images_included,
            "[capacidades] image_retrieval=true y todas las imagenes tienen included_in_package=true",
            "[capacidades][correccion-7] image_retrieval=true pero existen imagenes con included_in_package=false",
        )
        has_visual_index = any("imagen" in idx.get("covers_chunk_types", []) for idx in indexes)
        report.check(
            has_visual_index,
            "[capacidades] image_retrieval=true y existe al menos un indice que cubre chunk_type=imagen",
            "[capacidades][correccion-7] image_retrieval=true pero ningun indice en indexes.json declara covers_chunk_types incluyendo 'imagen'",
        )


def validate_acceptance_semantics(data: dict, report: Report) -> None:
    """[correccion-8, endurecido en rc3.1] Semantica ejecutable:
    top_k/match_policy/minimum_recall ya son exigidos por
    acceptance_case.schema.json; aqui se cruza cada caso contra
    access_hierarchy.json para que un caso de prueba no pueda esperar
    (expected_source_ids/expected_chunk_ids/expected_evidence_ids) algo por
    encima del nivel de acceso de la propia prueba, y para que
    `must_not_retrieve` no pueda "aprobar vacio" apuntando a un id que ni
    siquiera existe en el paquete.

    [rc3.1] rc3 solo aplicaba la verificacion de jerarquia de acceso a
    `expected_source_ids` -- un caso podia declarar `expected_chunk_ids`/
    `expected_evidence_ids` de una fuente `confidencial` con
    `expected_source_ids=[]` y pasar con 0 errores (hueco confirmado por
    auditoria independiente). Y `must_not_retrieve` no se validaba en
    absoluto -- un ID inexistente en esa lista tambien pasaba con 0
    errores, permitiendo una prueba de denegacion vacia."""
    hierarchy = data.get("access_hierarchy.json", {}) or {}
    order = hierarchy.get("order", [])
    sources = {s["id"]: s for s in data.get("sources.jsonl", [])}
    chunks = {c["id"]: c for c in data.get("chunks.jsonl", [])}
    evidence_by_id = {e["id"]: e for e in data.get("evidence.jsonl", [])}

    def level_index(level: str) -> int:
        return order.index(level) if level in order else -1

    def source_for_chunk(chunk_id: str) -> dict | None:
        c = chunks.get(chunk_id)
        return sources.get(c["source_id"]) if c else None

    def source_for_evidence(evidence_id: str) -> dict | None:
        # [rc3.2] se resuelve SIEMPRE via evidence.chunk_id -> chunk.source_id,
        # NUNCA via evidence.source_id directamente. rc3.1 usaba el campo
        # `source_id` de la propia evidencia, que es una copia declarada y
        # NO estaba verificada contra el chunk real -- una evidencia con
        # chunk_id apuntando a un chunk confidencial pero source_id
        # falseado a una fuente publica pasaba la verificacion de acceso
        # (auditoria independiente, confirmado con 0 errores antes de esta
        # correccion). validate_referential_integrity ademas rechaza ahora
        # cualquier evidence.source_id que no coincida con el source_id
        # real de su chunk, asi que esta funcion y ese chequeo son
        # defensas independientes para el mismo invariante.
        return source_for_chunk(e["chunk_id"]) if (e := evidence_by_id.get(evidence_id)) else None

    def check_access(case_id: str, label: str, obj_id: str, src: dict | None, user_idx: int, user_level: str) -> None:
        if src is None:
            report.error(f"[aceptacion] caso {case_id} -> {label} {obj_id} no se pudo resolver hasta una fuente existente")
            return
        src_idx = level_index(src.get("access_level"))
        report.check(
            user_idx >= 0 and src_idx >= 0 and src_idx <= user_idx,
            f"[aceptacion][correccion-8] caso {case_id}: {label} {obj_id} (fuente access_level={src.get('access_level')}) es autorizable para user_access_level={user_level}",
            f"[aceptacion][correccion-8][rc3.1] caso {case_id}: {label} {obj_id} (fuente access_level={src.get('access_level')}) EXCEDE el nivel de acceso de prueba user_access_level={user_level} -- caso mal formado",
        )

    for case in data.get("acceptance_cases.jsonl", []):
        case_id = case["case_id"]
        user_level = case.get("user_access_level")
        user_idx = level_index(user_level)
        report.check(
            user_idx >= 0,
            f"[aceptacion] caso {case_id}: user_access_level '{user_level}' existe en access_hierarchy.order",
            f"[aceptacion][correccion-8] caso {case_id}: user_access_level '{user_level}' NO existe en access_hierarchy.order",
        )

        for sid in case.get("expected_source_ids", []):
            check_access(case_id, "expected_source_id", sid, sources.get(sid), user_idx, user_level)

        for cid in case.get("expected_chunk_ids", []):
            report.check(
                cid in chunks,
                f"[aceptacion] caso {case_id} -> expected_chunk_id {cid} existe en el paquete",
                f"[aceptacion] caso {case_id} -> expected_chunk_id {cid} NO existe en el paquete",
            )
            if cid in chunks:
                # [rc3.1] antes solo se verificaba existencia -- ahora tambien
                # se resuelve hasta la fuente y se aplica la misma regla de
                # jerarquia que a expected_source_ids.
                check_access(case_id, "expected_chunk_id", cid, source_for_chunk(cid), user_idx, user_level)

        for eid in case.get("expected_evidence_ids", []):
            report.check(
                eid in evidence_by_id,
                f"[aceptacion] caso {case_id} -> expected_evidence_id {eid} existe en el paquete",
                f"[aceptacion] caso {case_id} -> expected_evidence_id {eid} NO existe en el paquete",
            )
            if eid in evidence_by_id:
                # [rc3.1] idem: resolver evidence -> chunk -> fuente y aplicar jerarquia.
                check_access(case_id, "expected_evidence_id", eid, source_for_evidence(eid), user_idx, user_level)

        # [rc3.1] must_not_retrieve NUEVO: cada id debe existir realmente
        # como source/chunk/evidence del paquete -- de lo contrario la
        # prueba de denegacion "aprueba vacio" prohibiendo algo que nunca
        # podria recuperarse de todos modos.
        known_ids = set(sources) | set(chunks) | set(evidence_by_id)
        for forbidden_id in case.get("must_not_retrieve", []):
            report.check(
                forbidden_id in known_ids,
                f"[aceptacion][rc3.1] caso {case_id}: must_not_retrieve {forbidden_id} existe en el paquete (source/chunk/evidence) -- prueba de denegacion no vacia",
                f"[aceptacion][rc3.1] caso {case_id}: must_not_retrieve {forbidden_id} NO existe como source/chunk/evidence del paquete -- prueba de denegacion vacia (prohibe algo que de todas formas no podria recuperarse)",
            )


def validate_checksums(pkg_dir: Path, report: Report) -> dict:
    checksums_path = pkg_dir / "checksums.json"
    if not checksums_path.exists():
        report.error("[checksums] falta checksums.json")
        return {}
    try:
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"[checksums] checksums.json es JSON invalido: {exc}")
        return {}
    declared = checksums.get("files", {})

    for fname, declared_hash in declared.items():
        fpath = pkg_dir / fname
        if not fpath.exists():
            report.error(f"[checksums] {fname} declarado pero ausente del paquete")
            continue
        try:
            if fname.endswith(".jsonl"):
                records = read_jsonl(fpath)
                sort_key = "case_id" if fname == "acceptance_cases.jsonl" else "id"
                recomputed = k.sha256_hex(k.canonical_jsonl_bytes(records, sort_key=sort_key))
            elif fname.endswith(".json"):
                obj = json.loads(fpath.read_text(encoding="utf-8"))
                recomputed = k.sha256_hex(k.canonical_json_bytes(obj))
            else:
                recomputed = k.sha256_hex(fpath.read_bytes())
        except (ValidationAborted, json.JSONDecodeError) as exc:
            report.error(f"[checksums] {fname} no se pudo recalcular: {exc}")
            continue
        report.check(
            recomputed == declared_hash,
            f"[checksums] {fname} coincide ({declared_hash[:12]}...)",
            f"[checksums] {fname} NO coincide -- declarado {declared_hash[:12]}..., recalculado {recomputed[:12]}...",
        )

    checksums_bytes = k.canonical_json_bytes(checksums)
    checksums_json_hash = k.sha256_hex(checksums_bytes)
    content_digest = k.content_digest(declared, checksums_json_hash)
    return {"checksums_json_hash": checksums_json_hash, "content_digest": content_digest}


def validate_signature_sidecar(
    digest_info: dict,
    content_digest_file,
    signature_file,
    public_key_file,
    trusted_key_id,
    zip_sha256_file,
    zip_path,
    report: Report,
) -> None:
    if not digest_info:
        return
    if content_digest_file:
        declared = content_digest_file.read_text(encoding="utf-8").strip()
        report.check(
            declared == digest_info["content_digest"],
            "[sidecar] *.content.sha256 coincide con content_digest recalculado",
            f"[sidecar] *.content.sha256 NO coincide -- declarado {declared[:12]}..., recalculado {digest_info['content_digest'][:12]}...",
        )
    else:
        report.ok.append("[sidecar] no se entrego --content-digest-file -- omitido (recomendado siempre en produccion)")

    if zip_sha256_file and zip_path:
        declared_zip_hash = zip_sha256_file.read_text(encoding="utf-8").strip()
        recomputed_zip_hash = k.sha256_hex(zip_path.read_bytes())
        report.check(
            declared_zip_hash == recomputed_zip_hash,
            "[sidecar] *.zip.sha256 coincide con el hash real de los bytes del .zip",
            f"[sidecar] *.zip.sha256 NO coincide -- declarado {declared_zip_hash[:12]}..., recalculado {recomputed_zip_hash[:12]}...",
        )

    if not signature_file:
        report.ok.append("[sidecar] no se entrego --signature-file -- firma no verificada en esta corrida")
        return

    try:
        sig = json.loads(signature_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"[sidecar][correccion-6] {signature_file.name} no es JSON valido: {exc}")
        return

    # [correccion-6] validar el sidecar CONTRA signature.schema.json ANTES
    # de usar cualquiera de sus campos.
    sig_schema = load_schema("signature.schema.json")
    sig_validator = make_validator(sig_schema)
    sig_errors = sorted(sig_validator.iter_errors(sig), key=lambda e: list(e.path))
    if sig_errors:
        for e in sig_errors:
            report.error(f"[sidecar][correccion-6] {signature_file.name} no cumple signature.schema.json: {'/'.join(str(p) for p in e.path)}: {e.message}")
        return
    report.ok.append(f"[sidecar][correccion-6] {signature_file.name} cumple signature.schema.json")

    report.check(
        sig.get("checksums_json_hash") == digest_info["checksums_json_hash"],
        "[sidecar] signature.checksums_json_hash coincide con checksums.json recalculado",
        "[sidecar] signature.checksums_json_hash NO coincide con checksums.json recalculado",
    )
    report.check(
        sig.get("content_digest") == digest_info["content_digest"],
        "[sidecar] signature.content_digest coincide con el paquete recalculado",
        "[sidecar] signature.content_digest NO coincide con el paquete recalculado",
    )

    if trusted_key_id:
        report.check(
            sig.get("key_id") == trusted_key_id,
            f"[firma][correccion-6] signature.key_id coincide con --trusted-key-id ({trusted_key_id})",
            f"[firma][correccion-6] signature.key_id ('{sig.get('key_id')}') NO coincide con --trusted-key-id ('{trusted_key_id}')",
        )

    if not public_key_file:
        report.ok.append(
            "[firma] signature presente pero no se entrego --public-key -- firma criptografica NO verificada. "
            "IMPORTANTE [correccion-6]: en produccion, Agent Runtime debe resolver la clave publica desde su PROPIO "
            "almacen de confianza (indexado por key_id), nunca aceptar una clave entregada junto con el paquete como prueba de identidad."
        )
        return
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    try:
        public_key = serialization.load_pem_public_key(public_key_file.read_bytes())
    except ValueError as exc:
        report.error(f"[firma] la clave publica entregada no se pudo cargar como PEM: {exc}")
        return
    if not isinstance(public_key, ed25519.Ed25519PublicKey):
        report.error("[firma] la clave publica entregada no es Ed25519")
        return
    to_verify = sig["checksums_json_hash"].encode("utf-8") + b":" + sig["content_digest"].encode("utf-8")
    try:
        public_key.verify(base64.b64decode(sig["signature"]), to_verify)
        report.ok.append(f"[firma] firma Ed25519 verificada con la clave publica entregada (key_id={sig.get('key_id')})")
    except InvalidSignature:
        report.error("[firma] la firma NO es valida para la clave publica entregada")


def run_validation(args) -> Report:
    report = Report()
    selfcheck_schemas(report)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = None
        if args.package.is_dir():
            pkg_dir = args.package
        elif args.package.suffix == ".zip":
            pkg_dir = Path(tmp)
            zip_path = args.package
            if not safe_extract_zip(args.package, pkg_dir, report):
                return report
        else:
            raise ValidationAborted(f"ruta no reconocida (ni directorio ni .zip): {args.package}")

        data = validate_schemas(pkg_dir, report)
        validate_referential_integrity(data, report)
        validate_lineage_continuity(data, report)
        validate_file_set_and_counts(pkg_dir, data, report)
        validate_profile_and_originals(pkg_dir, data, report)
        validate_capabilities_omissions(data, report)
        validate_acceptance_semantics(data, report)
        digest_info = validate_checksums(pkg_dir, report)
        validate_signature_sidecar(
            digest_info,
            args.content_digest_file,
            args.signature_file,
            args.public_key,
            args.trusted_key_id,
            args.zip_sha256_file,
            zip_path,
            report,
        )

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", type=Path)
    ap.add_argument("--content-digest-file", type=Path, default=None)
    ap.add_argument("--signature-file", type=Path, default=None)
    ap.add_argument("--public-key", type=Path, default=None)
    ap.add_argument("--trusted-key-id", type=str, default=None,
                     help="key_id esperado (defensa en profundidad -- NO sustituye un almacen de confianza real)")
    ap.add_argument("--zip-sha256-file", type=Path, default=None,
                     help="sha256 de los BYTES reales del .zip (distinto de content_digest, que es del contenido)")
    args = ap.parse_args()

    # Endurecimiento no bloqueante: nunca una traceback sin controlar --
    # cualquier entrada malformada produce un mensaje de error legible y
    # codigo de salida 1.
    try:
        report = run_validation(args)
    except ValidationAborted as exc:
        print(f"ERROR FATAL: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 -- ultimo recurso, nunca dejar pasar una traceback cruda
        print(f"ERROR FATAL inesperado: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return print_report(report)


def print_report(report: Report) -> int:
    print(f"OK: {len(report.ok)}")
    for m in report.ok:
        print(f"  [ok] {m}")
    print(f"ERRORES: {len(report.errors)}")
    for m in report.errors:
        print(f"  [ERROR] {m}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
