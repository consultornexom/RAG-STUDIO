"""NEXOM Knowledge Package v1.0-rc3 -- esquema de identificadores portables/
estables y utilidades de canonicalizacion.

Cambio de fondo respecto de rc2 (correccion 4 del tercer veredicto NEXOM):

  * `source_logical_id` YA NO se deriva caminando `supersedes_source_id`
    dentro de la exportacion actual. rc2 tenia un defecto real: si una
    exportacion futura solo incluye la version vigente de una fuente (sin
    su historial), el algoritmo de rc2 tomaria esa version como si fuera
    la raiz y generaria un `logical_id` DISTINTO del que tenia en una
    exportacion anterior que si incluia el historial -- rompiendo
    silenciosamente la identidad logica.

    En rc3, `lineage_id` es un valor OPACO Y PERSISTENTE: se asigna una
    sola vez cuando una fuente RAIZ se crea (UUID4, sin formula
    determinista), y toda fuente que la supersede HEREDA (copia) el mismo
    `lineage_id` de la version que reemplaza -- nunca se recalcula. Esto
    es responsabilidad de RAG Studio en RAG-INC-01 (un campo nuevo y
    persistido en el esquema real, analogo a `knowledge_base_id`): el
    exportador simplemente lo copia tal cual a `SourceRecord.logical_id`.

    El validador de referencia YA NO intenta "recomputar" `logical_id`
    desde el contenido (no se puede, es opaco por diseno) -- en su lugar
    verifica CONTINUIDAD DE CADENA: si A supersede a B y ambas estan en el
    mismo paquete, deben compartir `logical_id`. Ver
    `validator/validate_knowledge_package.py::validate_lineage_continuity`.

  * `content_digest` se calcula canonicalizando una ESTRUCTURA JSON (dict
    con `files` y `checksums_json_hash`) en vez de concatenar lineas
    "ruta:hash" con separadores de texto -- evita cualquier ambiguedad si
    algun nombre de archivo futuro contuviera ":" o un salto de linea.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Iterable, Optional

import rfc8785

# Namespace UUID fijo del contrato NEXOM Knowledge Package. Calculado UNA
# sola vez como uuid5(NAMESPACE_URL, "https://nexom.com/nexom-knowledge-package/v1")
# y congelado como constante. UUIDv5 conforme RFC 9562.
NEXOM_KP_NAMESPACE = uuid.UUID("9be25620-d2d4-5619-bdc9-4d223d551480")


def _uuid5(*parts: str) -> str:
    return str(uuid.uuid5(NEXOM_KP_NAMESPACE, ":".join(parts)))


def is_valid_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# knowledge_base_id: UUID4 generado una vez por el exportador (RAG-INC-01) y
# persistido junto al proyecto. No se calcula aqui.
# ---------------------------------------------------------------------------

def is_valid_knowledge_base_id(value: str) -> bool:
    return is_valid_uuid(value)


# ---------------------------------------------------------------------------
# Identidad de fuente: `lineage_id` es OPACO (no se deriva de nada) --
# ver docstring del modulo. Estas funciones solo dan FORMA al URN portable
# y calculan la identidad de VERSION (que si es determinista, a partir del
# lineage_id + el contenido).
# ---------------------------------------------------------------------------

def portable_source_logical_id(lineage_id: str) -> str:
    return f"urn:nexom:source-logical:{lineage_id}"


def source_version_key(content_hash: Optional[str], title: str, source_type: str, updated_at_iso: str) -> str:
    if content_hash:
        return f"content:{content_hash}"
    return f"noncontent:{title}|{source_type}|{updated_at_iso}"


def source_version_id(lineage_id: str, version_key: str) -> str:
    return _uuid5("source-version", lineage_id, version_key)


def portable_source_id(lineage_id: str, version_key: str) -> str:
    return f"urn:nexom:source:{source_version_id(lineage_id, version_key)}"


# ---------------------------------------------------------------------------
# Chunks -- fingerprint de 256 bits (sha256 completo, sin truncar).
# ---------------------------------------------------------------------------

def chunk_fingerprint(chunk_index: int, text: str) -> str:
    return hashlib.sha256(f"{chunk_index}:{text}".encode("utf-8")).hexdigest()


def portable_chunk_id(portable_src_id: str, chunk_index: int, text: str) -> str:
    version_uuid = portable_src_id.rsplit(":", 1)[-1]
    return f"urn:nexom:chunk:{version_uuid}:{chunk_fingerprint(chunk_index, text)}"


def portable_evidence_id(portable_chunk: str, evidence_kind: str) -> str:
    return f"urn:nexom:evidence:{_uuid5('evidence', portable_chunk, evidence_kind)}"


def portable_media_id(portable_chunk: str, checksum: str) -> str:
    return f"urn:nexom:media:{_uuid5('media', portable_chunk, checksum)}"


# ---------------------------------------------------------------------------
# IDs escalados por knowledge_base_id.
# ---------------------------------------------------------------------------

def portable_catalog_id(knowledge_base_id: str, catalog_name: str) -> str:
    return f"urn:nexom:catalog:{_uuid5('catalog', knowledge_base_id, catalog_name)}"


def portable_intent_id(knowledge_base_id: str, name: str) -> str:
    return f"urn:nexom:intent:{_uuid5('intent', knowledge_base_id, name)}"


def portable_guardrail_id(knowledge_base_id: str, name: str) -> str:
    return f"urn:nexom:guardrail:{_uuid5('guardrail', knowledge_base_id, name)}"


def portable_variable_id(knowledge_base_id: str, code: str) -> str:
    return f"urn:nexom:variable:{_uuid5('variable', knowledge_base_id, code)}"


def portable_channeling_id(knowledge_base_id: str, code: str) -> str:
    return f"urn:nexom:channeling:{_uuid5('channeling', knowledge_base_id, code)}"


def portable_field_definition_id(knowledge_base_id: str, field_code: str) -> str:
    """El ID relacional REAL de un campo de metadata. `field_code`
    (ej. "campus") es local y legible -- viaja aparte, como atributo
    informativo, NUNCA como clave de relacion (correccion 5 del tercer
    veredicto: source_metadata.jsonl y Chunk.inherited_metadata deben
    referenciar esto, no el codigo local)."""
    return f"urn:nexom:field:{_uuid5('field', knowledge_base_id, field_code)}"


# ---------------------------------------------------------------------------
# Canonicalizacion -- RFC 8785 (JSON Canonicalization Scheme) real.
# ---------------------------------------------------------------------------

def canonical_json_bytes(obj: Any) -> bytes:
    return rfc8785.dumps(obj) + b"\n"


def canonical_jsonl_bytes(records: Iterable[dict], sort_key: str = "id") -> bytes:
    lines = [rfc8785.dumps(r) for r in sorted(records, key=lambda r: r.get(sort_key, ""))]
    body = b"\n".join(lines)
    return (body + b"\n") if lines else b""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_digest(file_hashes: dict[str, str], checksums_json_hash: str) -> str:
    """Digesto canonico de TODO el contenido del paquete, calculado
    canonicalizando una ESTRUCTURA JSON (rc3 -- en rc2 se concatenaba
    texto "ruta:hash", lo que en teoria podia ser ambiguo si un nombre de
    archivo contuviera ':'). `signature.json`/`*.sig` NUNCA se incluyen
    aqui -- viven fuera del paquete y firman este valor, no al reves."""
    payload = {"checksums_json_hash": checksums_json_hash, "files": file_hashes}
    return sha256_hex(canonical_json_bytes(payload))
