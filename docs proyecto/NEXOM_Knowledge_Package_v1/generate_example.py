"""Genera el paquete de ejemplo valido v1.0-rc3.2 (perfil CORE) del NEXOM
Knowledge Package, usando la implementacion de referencia de id_scheme.py.

IMPORTANTE (rc3.2, correccion documental): RC_TAG/SCHEMA_VERSION/FILE_TAG
de abajo son la UNICA fuente de verdad para la cadena de version -- se
usan para manifest.schema_version, exporter_version, el nombre base de los
sidecars, signature.key_id y signature.signer. Una auditoria independiente
encontro que en rc3.1 estas cadenas seguian diciendo "rc3" en varios
lugares mientras el ADR/LEEME ya declaraban "rc3.1", lo que habria hecho
ambiguo el informe firmado de AR-INC-00 (que debe certificar la version
indicada por schema_version). No volver a hardcodear el sufijo de version
en mas de un lugar.

Cambios respecto de rc2 (vigentes desde rc3):
  - `lineage_id` es OPACO y se COPIA al superseder (no se deriva de una
    cadena origin_id) -- simula lo que RAG-INC-01 haria en RAG Studio.
  - source_metadata.jsonl y Chunk.inherited_metadata referencian
    `field_definition_id` (URN), no el codigo local.
  - manifest.omissions incluye EVIDENCE_NOT_VERIFIED (toda la evidencia de
    este ejemplo es 'derived').
  - Se agrega access_hierarchy.json.
  - acceptance_cases.jsonl incluye top_k/match_policy/minimum_recall.
  - content_digest via estructura JSON canonica (no concatenacion de texto).
  - El sidecar de digesto se llama '<paquete>.content.sha256' (ya no
    ambiguo con un hash del ZIP en si).

Uso: python3 generate_example.py <dir_common> <dir_paquete> <dir_sidecars>
"""
from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import id_scheme as k  # noqa: E402

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

PKG_DIR = Path(sys.argv[2])
SIDECAR_DIR = Path(sys.argv[3])
PKG_DIR.mkdir(parents=True, exist_ok=True)
SIDECAR_DIR.mkdir(parents=True, exist_ok=True)

RC_TAG = "rc3.2"  # unica fuente de verdad para el sufijo de version -- ver nota de rc3.2 en el docstring del modulo
SCHEMA_VERSION = f"1.0.0-{RC_TAG}"  # manifest.schema_version / exporter_version
FILE_TAG = f"v1.0-{RC_TAG}"  # nombre de sidecars/paquete y textos "v1.0-rc3.2" (estilo ADR/LEEME/zip)

KNOWLEDGE_BASE_ID = "5f9d5e2a-7b4a-4e1a-9c3a-1a2b3c4d5e6f"  # generado UNA vez, demo
PROJECT_ID_ORIGIN = "proj-demo-admisiones-2026"  # NO se usa en ninguna formula de ID
NOW = "2026-09-21T12:00:00+00:00"
ORIGINAL_SIZE_LIMIT_BYTES = 50 * 1024 * 1024  # 50 MB -- politica FIJA de v1.0 (rc3, punto 2)

# ---------------------------------------------------------------------------
# 1. Sources. `lineage_id` se asigna una vez (raiz) y se COPIA al
#    superseder -- ya NO se deriva caminando origin_id (rc3, correccion 4).
# ---------------------------------------------------------------------------
LINEAGE_REGLAMENTO = str(uuid.uuid4())
LINEAGE_CATALOGO = str(uuid.uuid4())
LINEAGE_NOTAS = str(uuid.uuid4())

raw_sources = [
    {  # src1_old, raiz del linaje "reglamento"
        "origin_id": "a1b2c3d4-0001-4000-8000-000000000001",
        "lineage_id": LINEAGE_REGLAMENTO,
        "title": "Reglamento de Admisiones 2025", "source_type": "pdf",
        "owner_area": "Direccion de Admisiones", "access_level": "publico", "language": "es",
        "content_hash": "7a1e2f3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f",
        "validation_status": "vencido", "valid_from": "2025-01-01", "valid_to": "2025-12-31",
        "source_authority": 1, "document_type_code": "reglamento", "supersedes_origin_id": None,
        "created_at": "2025-01-01T00:00:00+00:00", "updated_at": "2025-01-01T00:00:00+00:00",
    },
    {  # src1, vigente -- COPIA el lineage_id de src1_old, no lo recalcula
        "origin_id": "a1b2c3d4-0002-4000-8000-000000000002",
        "lineage_id": LINEAGE_REGLAMENTO,
        "title": "Reglamento de Admisiones 2026", "source_type": "pdf",
        "owner_area": "Direccion de Admisiones", "access_level": "publico", "language": "es",
        "content_hash": "b3f1c2a9e6d4f0a1b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5",
        "validation_status": "validado", "valid_from": "2026-01-01", "valid_to": None,
        "source_authority": 1, "document_type_code": "reglamento",
        "supersedes_origin_id": "a1b2c3d4-0001-4000-8000-000000000001",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": NOW,
    },
    {  # src2, linaje propio
        "origin_id": "a1b2c3d4-0003-4000-8000-000000000003",
        "lineage_id": LINEAGE_CATALOGO,
        "title": "Catalogo de Programas Academicos", "source_type": "xlsx",
        "owner_area": "Direccion Academica", "access_level": "publico", "language": "es",
        "content_hash": "9e8d7c6b5a4938271605f4e3d2c1b0a9887766554433221100ffeeddccbbaa9",
        "validation_status": "validado", "valid_from": "2026-01-01", "valid_to": None,
        "source_authority": 1, "document_type_code": "catalogo", "supersedes_origin_id": None,
        "created_at": NOW, "updated_at": NOW,
    },
    {  # src_confidencial, linaje propio
        "origin_id": "a1b2c3d4-0004-4000-8000-000000000004",
        "lineage_id": LINEAGE_NOTAS,
        "title": "Notas internas del comite de admisiones", "source_type": "docx",
        "owner_area": "Direccion de Admisiones", "access_level": "confidencial", "language": "es",
        "content_hash": "1122334455667788990011223344556677889900112233445566778899aabb",
        "validation_status": "validado", "valid_from": "2026-01-01", "valid_to": None,
        "source_authority": 2, "document_type_code": "acta_interna", "supersedes_origin_id": None,
        "created_at": NOW, "updated_at": NOW,
    },
]

sources: list[dict] = []
portable_by_origin: dict[str, str] = {}
logical_by_origin: dict[str, str] = {}

for row in raw_sources:
    logical_urn = k.portable_source_logical_id(row["lineage_id"])
    version_key = k.source_version_key(row["content_hash"], row["title"], row["source_type"], row["updated_at"])
    portable_id = k.portable_source_id(row["lineage_id"], version_key)
    portable_by_origin[row["origin_id"]] = portable_id
    logical_by_origin[row["origin_id"]] = logical_urn
    sources.append({
        "id": portable_id, "logical_id": logical_urn, "origin_id": row["origin_id"],
        "title": row["title"], "source_type": row["source_type"], "owner_area": row["owner_area"],
        "access_level": row["access_level"], "language": row["language"],
        "content_hash": row["content_hash"], "validation_status": row["validation_status"],
        "valid_from": row["valid_from"], "valid_to": row["valid_to"],
        "source_authority": row["source_authority"], "supersedes_source_id": None,
        "document_type_code": row["document_type_code"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "original_included": False,
        "original_omission_reason": "not_applicable_profile_core",
        "original_media_type": None, "original_checksum": None, "original_relative_path": None,
    })

for s, row in zip(sources, raw_sources):
    if row["supersedes_origin_id"]:
        s["supersedes_source_id"] = portable_by_origin[row["supersedes_origin_id"]]

src1_old_id, src1_id, src2_id, src_conf_id = (
    portable_by_origin["a1b2c3d4-0001-4000-8000-000000000001"],
    portable_by_origin["a1b2c3d4-0002-4000-8000-000000000002"],
    portable_by_origin["a1b2c3d4-0003-4000-8000-000000000003"],
    portable_by_origin["a1b2c3d4-0004-4000-8000-000000000004"],
)
assert logical_by_origin["a1b2c3d4-0001-4000-8000-000000000001"] == logical_by_origin["a1b2c3d4-0002-4000-8000-000000000002"], \
    "src1_old y src1 DEBEN compartir logical_id (mismo lineage_id copiado, no recalculado)"

# ---------------------------------------------------------------------------
# 2. Metadata schema (necesaria ANTES de los chunks -- inherited_metadata
#    ahora se referencia por field_definition_id).
# ---------------------------------------------------------------------------
campus_catalog_id = k.portable_catalog_id(KNOWLEDGE_BASE_ID, "campus")
programa_catalog_id = k.portable_catalog_id(KNOWLEDGE_BASE_ID, "programa")
campus_field_id = k.portable_field_definition_id(KNOWLEDGE_BASE_ID, "campus")
programa_field_id = k.portable_field_definition_id(KNOWLEDGE_BASE_ID, "programa")

metadata_schema = {
    "schema_version_local": 3,
    "knowledge_base_id": KNOWLEDGE_BASE_ID,
    "fields": [
        {"id": campus_field_id, "field_id": "campus", "display_name": "Campus",
         "data_type": "seleccion_unica", "required": True, "filterable": True, "multiple": False,
         "inherited_by_chunks": True, "catalog_id": campus_catalog_id},
        {"id": programa_field_id, "field_id": "programa", "display_name": "Programa academico",
         "data_type": "seleccion_unica", "required": True, "filterable": True, "multiple": False,
         "inherited_by_chunks": True, "catalog_id": programa_catalog_id},
    ],
    "catalogs": [
        {"id": campus_catalog_id, "name": "campus", "entries": [
            {"value_code": "LEON", "label": "Leon", "parent_entry_code": None},
            {"value_code": "IRAPUATO", "label": "Irapuato", "parent_entry_code": None},
        ]},
        {"id": programa_catalog_id, "name": "programa", "entries": [
            {"value_code": "DER", "label": "Derecho", "parent_entry_code": None},
            {"value_code": "ISC", "label": "Ingenieria en Sistemas", "parent_entry_code": None},
        ]},
    ],
}

source_metadata = [
    {"id": f"{src1_id}:{campus_field_id}", "source_id": src1_id, "field_definition_id": campus_field_id,
     "field_code": "campus", "value": ["LEON"], "created_at": NOW},
    {"id": f"{src1_id}:{programa_field_id}", "source_id": src1_id, "field_definition_id": programa_field_id,
     "field_code": "programa", "value": ["DER"], "created_at": NOW},
]

# ---------------------------------------------------------------------------
# 3. Chunks
# ---------------------------------------------------------------------------
def mk_chunk(portable_src_id, idx, text, chunk_type="texto", **extra):
    cid = k.portable_chunk_id(portable_src_id, idx, text)
    base = {
        "id": cid, "source_id": portable_src_id, "chunk_index": idx, "text": text,
        "token_count": max(1, len(text.split())), "chunk_type": chunk_type,
        "section_title": extra.pop("section_title", None),
        "page_start": extra.pop("page_start", None), "page_end": extra.pop("page_end", None),
        "previous_chunk_id": None, "next_chunk_id": None, "parent_chunk_id": None,
        "structured_content": extra.pop("structured_content", None),
        "semantic_summary": extra.pop("semantic_summary", None),
        "inherited_metadata": extra.pop("inherited_metadata", {}), "created_at": NOW,
    }
    base.update(extra)
    return base


c0 = mk_chunk(src1_id, 0, "Capitulo 3. Requisitos de ingreso.", chunk_type="encabezado",
              section_title="Capitulo 3", page_start=5, page_end=5)
c1 = mk_chunk(src1_id, 1,
              "El aspirante debe entregar acta de nacimiento, certificado de bachillerato y "
              "comprobante de pago de ficha de admision antes de la fecha limite publicada.",
              chunk_type="texto", section_title="Capitulo 3", page_start=5, page_end=5,
              inherited_metadata={campus_field_id: "LEON", programa_field_id: "DER"})
c2 = mk_chunk(src1_id, 2,
              "Los aspirantes de programas de posgrado deben ademas presentar titulo de "
              "licenciatura y examen de admision con calificacion minima de 70.",
              chunk_type="texto", section_title="Capitulo 3", page_start=6, page_end=6,
              inherited_metadata={campus_field_id: "LEON", programa_field_id: "DER"})
c0["next_chunk_id"] = c1["id"]
c1["previous_chunk_id"] = c0["id"]
c1["parent_chunk_id"] = c0["id"]
c1["next_chunk_id"] = c2["id"]
c2["previous_chunk_id"] = c1["id"]
c2["parent_chunk_id"] = c0["id"]

c3 = mk_chunk(src2_id, 0, "Tabla de programas vigentes por campus y modalidad.",
              chunk_type="tabla", section_title="Programas 2026",
              structured_content={
                  "columns": ["programa", "campus", "modalidad", "duracion_semestres"],
                  "rows": [["Derecho", "Leon", "Presencial", 9], ["Ingenieria en Sistemas", "Irapuato", "Hibrida", 9]],
              })

c4 = mk_chunk(src1_id, 3, "", chunk_type="imagen", section_title="Capitulo 3", page_start=7, page_end=7,
              image_relative_path="assets/images/reglamento_diagrama_flujo.png")

c5 = mk_chunk(src_conf_id, 0,
              "Acuerdo interno: los casos limite de promedio se resuelven por comite, no por sistema.",
              chunk_type="texto", section_title="Acuerdos internos", page_start=1, page_end=1)

chunks = [c0, c1, c2, c3, c4, c5]

# ---------------------------------------------------------------------------
# 4. Evidence -- toda 'derived' en este ejemplo (ninguna verificada
#    editorialmente) -- por eso el manifiesto declarara EVIDENCE_NOT_VERIFIED.
# ---------------------------------------------------------------------------
def mk_evidence(chunk, source_row):
    kind = "citation_anchor"
    eid = k.portable_evidence_id(chunk["id"], kind)
    return {
        "id": eid, "evidence_kind": kind, "derivation_method": "derived_from_chunk_source",
        "verification_status": "derived", "source_id": source_row["id"], "chunk_id": chunk["id"],
        "page_range": [chunk.get("page_start"), chunk.get("page_end")],
        "section_title": chunk.get("section_title"),
        "content_hash": k.sha256_hex(chunk["text"].encode("utf-8")) if chunk["text"] else None,
        "source_authority": source_row["source_authority"],
        "source_valid_from": source_row["valid_from"], "source_valid_to": source_row["valid_to"],
    }

src_by_id = {s["id"]: s for s in sources}
evidence = [
    mk_evidence(c1, src_by_id[src1_id]), mk_evidence(c2, src_by_id[src1_id]),
    mk_evidence(c3, src_by_id[src2_id]), mk_evidence(c5, src_by_id[src_conf_id]),
]

# ---------------------------------------------------------------------------
# 5. Media (perfil CORE: solo descriptor)
# ---------------------------------------------------------------------------
media = [{
    "id": k.portable_media_id(c4["id"], "sha256:placeholder-image-hash-0001"),
    "media_type": "image", "chunk_id": c4["id"], "source_id": src1_id,
    "relative_path": "assets/images/reglamento_diagrama_flujo.png",
    "checksum": "sha256:placeholder-image-hash-0001", "included_in_package": False,
    "note": "Perfil CORE: solo descriptor. El binario se incluye bajo perfil AUDIT.",
}]

# ---------------------------------------------------------------------------
# 6. Conversational bundle
# ---------------------------------------------------------------------------
var_code = "folio_aspirante"
chan_code = "admisiones_humano"

conversational_bundle = {
    "intents": [{
        "id": k.portable_intent_id(KNOWLEDGE_BASE_ID, "requisitos_admision"), "name": "requisitos_admision",
        "description": "El aspirante pregunta por los requisitos para ingresar.",
        "positive_examples": ["que necesito para inscribirme", "requisitos de admision"],
        "negative_examples": ["cuanto cuesta la colegiatura"], "priority": 10, "risk_level": "bajo",
        "required_variables": [k.portable_variable_id(KNOWLEDGE_BASE_ID, var_code)], "optional_variables": [],
        "clarifying_questions": {k.portable_variable_id(KNOWLEDGE_BASE_ID, var_code): "Cual es tu folio de aspirante?"},
        "response_rule": "Responder con base en el Reglamento de Admisiones vigente.",
        "fallback_channeling_code": k.portable_channeling_id(KNOWLEDGE_BASE_ID, chan_code),
        "resolution_mode": "semantico", "active": True, "created_at": NOW, "updated_at": NOW,
    }],
    "guardrail_rules": [{
        "id": k.portable_guardrail_id(KNOWLEDGE_BASE_ID, "no_prometer_admision"), "name": "no_prometer_admision",
        "rule_type": "abstencion",
        "conditions": [{"field": "intencion", "operator": "=", "value": "requisitos_admision"}],
        "action": "aclarar", "priority": 5, "active": True, "created_at": NOW, "updated_at": NOW,
    }],
    "conversational_variables": [{
        "id": k.portable_variable_id(KNOWLEDGE_BASE_ID, var_code), "code": var_code, "display_name": "Folio de aspirante",
    }],
    "channeling_schemes": [{
        "id": k.portable_channeling_id(KNOWLEDGE_BASE_ID, chan_code), "code": chan_code, "medium": "correo",
        "summary_template": "Aspirante solicita atencion humana sobre admisiones.",
    }],
}

# ---------------------------------------------------------------------------
# 7. Embedding spaces + indexes
# ---------------------------------------------------------------------------
embedding_spaces = [{
    "id": "text_semantic_384", "modality": "text", "provider": "fastembed",
    "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "revision": None,
    "dimensions": 384, "normalization": "unknown_not_verified",
    "preprocessing": {"query_prefix": None, "passage_prefix": None},
    "distance_metric": "cosine", "dtype": "float32", "fingerprint": None,
}]
indexes = [{
    "id": "chunks_text_semantic_384", "embedding_space_id": "text_semantic_384", "index_type": "flat_cosine",
    "points_count": 5, "covers_chunk_types": ["texto", "tabla", "encabezado"], "updated_at": NOW,
}]

# ---------------------------------------------------------------------------
# 8. Access hierarchy (nuevo en rc3)
# ---------------------------------------------------------------------------
access_hierarchy = {
    "order": ["publico", "interno", "confidencial", "restringido"],
    "rule": ("Un usuario con user_access_level X puede acceder a fuentes cuyo access_level tenga "
             "indice <= indice(X) en `order`. Denegacion por defecto: cualquier access_level no "
             "reconocido, o ausencia de user_access_level, deniega el acceso -- nunca se asume el "
             "nivel mas permisivo."),
}

# ---------------------------------------------------------------------------
# 9. Acceptance cases (AR-INC-00) -- con semantica ejecutable (rc3).
# ---------------------------------------------------------------------------
acceptance_cases = [
    {
        "case_id": "AC-001-requisitos-admision", "query": "que necesito para inscribirme",
        "user_access_level": "publico", "top_k": 5, "match_policy": "contains", "minimum_recall": 1.0,
        "expected_source_ids": [src1_id],
        "expected_chunk_ids": [c1["id"], c2["id"]],
        "expected_evidence_ids": [mk_evidence(c1, src_by_id[src1_id])["id"], mk_evidence(c2, src_by_id[src1_id])["id"]],
        "expected_guardrail_decision": "aclarar", "must_not_retrieve": [],
        "notes": "Debe disparar el guardrail no_prometer_admision (action=aclarar) por la intencion requisitos_admision.",
    },
    {
        "case_id": "AC-002-catalogo-programas", "query": "que programas hay en Leon",
        "user_access_level": "publico", "top_k": 3, "match_policy": "contains", "minimum_recall": 1.0,
        "expected_source_ids": [src2_id],
        "expected_chunk_ids": [c3["id"]], "expected_evidence_ids": [mk_evidence(c3, src_by_id[src2_id])["id"]],
        "expected_guardrail_decision": None, "must_not_retrieve": [],
        "notes": "Consulta sobre contenido tabular (structured_content), sin guardrail aplicable.",
    },
    {
        "case_id": "AC-003-denegacion-por-acceso", "query": "que dicen las notas internas del comite",
        "user_access_level": "publico", "top_k": 5, "match_policy": "exact", "minimum_recall": 1.0,
        "expected_source_ids": [], "expected_chunk_ids": [], "expected_evidence_ids": [],
        "expected_guardrail_decision": None, "must_not_retrieve": [c5["id"], src_conf_id],
        "notes": "La fuente es access_level=confidencial (ver access_hierarchy.json); un usuario publico "
                 "NUNCA debe recibir este chunk ni esta fuente citados -- denegacion por defecto, no lista negra.",
    },
]

# ---------------------------------------------------------------------------
# 10. Manifest + escritura + checksums + sidecars firmados (FUERA del paquete)
# ---------------------------------------------------------------------------
files_content: dict[str, bytes] = {}
files_content["sources.jsonl"] = k.canonical_jsonl_bytes(sources, sort_key="id")
files_content["chunks.jsonl"] = k.canonical_jsonl_bytes(chunks, sort_key="id")
files_content["source_metadata.jsonl"] = k.canonical_jsonl_bytes(source_metadata, sort_key="id")
files_content["metadata_schema.json"] = k.canonical_json_bytes(metadata_schema)
files_content["evidence.jsonl"] = k.canonical_jsonl_bytes(evidence, sort_key="id")
files_content["media.jsonl"] = k.canonical_jsonl_bytes(media, sort_key="id")
files_content["conversational_bundle.json"] = k.canonical_json_bytes(conversational_bundle)
files_content["embedding_spaces.json"] = k.canonical_json_bytes(embedding_spaces)
files_content["indexes.json"] = k.canonical_json_bytes(indexes)
files_content["acceptance_cases.jsonl"] = k.canonical_jsonl_bytes(acceptance_cases, sort_key="case_id")
files_content["access_hierarchy.json"] = k.canonical_json_bytes(access_hierarchy)

manifest = {
    "package_id": "urn:nexom:package:" + k.sha256_hex(f"{KNOWLEDGE_BASE_ID}:v1:{NOW}".encode())[:32],
    "schema_version": SCHEMA_VERSION,
    "knowledge_version": "1",
    "created_at": NOW,
    "source_system": "rag-studio",
    "exporter_version": f"0.0.0-preview-rag-inc-00-{RC_TAG}",
    "tenant": "nexom-demo",
    "knowledge_base_id": KNOWLEDGE_BASE_ID,
    "project_id_origin": PROJECT_ID_ORIGIN,
    "project_revision": "rev-0007",
    "snapshot_id": "snapshot-demo-0001",
    "parent_package_id": None,
    "profile": "CORE",
    "counts": {
        "sources": len(sources), "chunks": len(chunks), "evidence": len(evidence), "media": len(media),
        "intents": len(conversational_bundle["intents"]),
        "guardrail_rules": len(conversational_bundle["guardrail_rules"]),
        "acceptance_cases": len(acceptance_cases),
    },
    "files": sorted(files_content.keys()) + ["manifest.json", "checksums.json"],
    "capabilities": {"text_retrieval": True, "structured_retrieval": True, "image_retrieval": False},
    "omissions": [
        {"code": "MEDIA_BINARIES_NOT_INCLUDED",
         "description": "Perfil CORE: media.jsonl declara 1 imagen pero el binario no viaja en el paquete."},
        {"code": "ORIGINALS_NOT_INCLUDED",
         "description": "Perfil CORE: ninguna fuente incluye su archivo original (original_included=false en todas)."},
        {"code": "VECTORS_NOT_INCLUDED",
         "description": "v1.0 no transporta vectores en perfil CORE/AUDIT; Agent Runtime reindexa desde chunks.jsonl."},
        {"code": "EVIDENCE_NOT_VERIFIED",
         "description": "Los 4 registros de evidence.jsonl tienen verification_status=derived -- ninguno fue "
                         "verificado editorialmente (RAG Studio no tiene hoy ese flujo)."},
    ],
}
files_content["manifest.json"] = k.canonical_json_bytes(manifest)

for name, data in files_content.items():
    (PKG_DIR / name).write_bytes(data)

checksums = {
    "algorithm": "sha256", "canonicalization": "rfc8785",
    "files": {name: k.sha256_hex(data) for name, data in files_content.items()},
}
checksums_bytes = k.canonical_json_bytes(checksums)
(PKG_DIR / "checksums.json").write_bytes(checksums_bytes)
checksums_json_hash = k.sha256_hex(checksums_bytes)

digest = k.content_digest(checksums["files"], checksums_json_hash)

package_name = f"nexom-knowledge-package-demo-{FILE_TAG}"
(SIDECAR_DIR / f"{package_name}.content.sha256").write_text(digest + "\n", encoding="utf-8")

private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()
to_sign = checksums_json_hash.encode("utf-8") + b":" + digest.encode("utf-8")
signature_bytes = private_key.sign(to_sign)

signature = {
    "algorithm": "ed25519", "key_id": f"demo-key-rag-inc-00-{RC_TAG}-NO-USAR-EN-PRODUCCION",
    "signer": f"RAG Studio (paquete de ejemplo, RAG-INC-00 {FILE_TAG})", "signed_at": NOW,
    "checksums_json_hash": checksums_json_hash, "content_digest": digest,
    "signature": base64.b64encode(signature_bytes).decode("ascii"),
}
(SIDECAR_DIR / f"{package_name}.sig").write_bytes(k.canonical_json_bytes(signature))

pub_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
(SIDECAR_DIR / f"{package_name}.pubkey_DEMO.pem").write_bytes(pub_pem)

print("Paquete generado en", PKG_DIR)
print("Sidecars en", SIDECAR_DIR)
print("knowledge_base_id:", KNOWLEDGE_BASE_ID)
print("package_id:", manifest["package_id"])
print("content_digest:", digest)
print("src1_old.logical_id == src1.logical_id ?",
      logical_by_origin["a1b2c3d4-0001-4000-8000-000000000001"] == logical_by_origin["a1b2c3d4-0002-4000-8000-000000000002"])
print("ORIGINAL_SIZE_LIMIT_BYTES (politica v1.0 fija):", ORIGINAL_SIZE_LIMIT_BYTES)
