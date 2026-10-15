"""Exportador CORE del NEXOM Knowledge Package v1.0.0 (RAG-INC-01b).

Fuente de verdad: el contrato firmado en
`docs proyecto/NEXOM_Knowledge_Package_v1/contrato_v1.0.0/` y el mapeo
archivo por archivo del Alcance firmado de RAG-INC-01 (§5). Las fórmulas de
identidad, la canonicalización RFC 8785 y `content_digest` vienen de la
implementación de referencia `id_scheme.py` firmada, vendorizada byte a byte
en `contracts/nexom_knowledge_package/v1_0_0/` (RAG-INC-01c), nunca
reimplementadas aquí.

Flujo:

1. Instantánea: la carpeta registrada (`snapshot_dir`) y su `project.db`
   deben existir. Se COPIA el `project.db` (y su `-wal`, si lo hay) a un
   temporal y solo se lee la copia: la instantánea nunca se abre ni se
   modifica (ni siquiera se crea un `-shm` en ella).
2. Compuertas previas (cualquiera aborta sin escribir en `output_dir`):
   proyecto de la copia = proyecto del registro; esquema con identidades
   persistentes (0021); `knowledge_base_id` y `lineage_id` válidos;
   `content_hash` presente en toda fuente basada en archivo (INC01-R1);
   índice presente; referencias internas resolubles; restricciones del
   contrato (texto de chunks no imagen); ids portables sin duplicados.
3. Staging en `output_dir/.nkp-staging-<uuid>/`: 13 archivos internos,
   `checksums.json`, ZIP determinista y verificación del ZIP recién escrito.
   RAG-INC-01c: compuerta de conformidad obligatoria (validador firmado
   v1.0.0 + comprobaciones de unicidad, `nkp_conformance.py`) sobre el ZIP y
   su sidecar; si no es PASS, ContractConformanceError y no se publica nada.
4. Publicación sin sobrescribir: el ZIP y luego el sidecar
   `<paquete>.content.sha256` (fuera del paquete). Si algo falla, se borra
   lo publicado y el staging.

Determinismo: misma instantánea + mismo tenant + mismo contrato + misma
EXPORTER_VERSION ⇒ mismos archivos, mismo `content_digest`, mismo
`package_id` y mismo ZIP byte a byte (fechas del ZIP fijas, entradas
ordenadas, compresión fija). `manifest.created_at` = fecha de la instantánea.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import rfc8785

from domain.documents.entities import _ACCESS_LEVEL_RANK, NON_FILE_SOURCE_TYPES, AccessLevel
from domain.knowledge_package.entities import (
    CONTRACT_SCHEMA_VERSION,
    PROFILE_CORE,
    KnowledgePackageExportResult,
    SnapshotDescriptor,
)
from domain.knowledge_package.exceptions import (
    BrokenReferenceError,
    ContractConformanceError,
    ContractConstraintError,
    MissingContentHashError,
    MissingIdentityError,
    OutputExistsError,
    PortableIdentityCollisionError,
    SnapshotDirectoryMissingError,
    SnapshotInconsistentError,
)
from domain.knowledge_package.conformance import ConformanceReport
from domain.knowledge_package.ports import KnowledgePackageConformanceValidator, KnowledgePackageExporter

from contracts.nexom_knowledge_package import load_id_scheme

logger = logging.getLogger(__name__)

k = load_id_scheme()

EXPORTER_VERSION = "1.0.0"
"""Versión propia del exportador NKP (Alcance §4, hito 01b). Se incrementa
solo cuando cambia su salida; no es la versión de `ragstudio`."""

_NON_FILE_VALUES = frozenset(t.value for t in NON_FILE_SOURCE_TYPES)
_NO_INDEXABLES = frozenset({"padre", "imagen"})
"""Tipos de chunk que no van al índice de texto: PADRE nunca se indexa
(application/rag/commands/index_source.py) e IMAGEN va a la colección de
imágenes, fuera del perfil CORE."""

_ACCESS_RULE = (
    "Un usuario con user_access_level X puede acceder a fuentes cuyo access_level tenga indice <= "
    "indice(X) en `order`. Denegacion por defecto: cualquier access_level no reconocido, o ausencia "
    "de user_access_level, deniega el acceso -- nunca se asume el nivel mas permisivo."
)
"""Constante `rule` de access_hierarchy.schema.json (valor `const` del contrato)."""

_PREFIJOS_POR_MODELO: dict[str, dict[str, Optional[str]]] = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {"query_prefix": None, "passage_prefix": None},
    "intfloat/multilingual-e5-large": {"query_prefix": "query: ", "passage_prefix": "passage: "},
}
"""Preprocesamiento conocido de los perfiles de embeddings de RAG Studio
(infrastructure/embeddings/fastembed_provider.py). Modelo desconocido ⇒ null."""

_UUID_CONTRATO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
"""Patrón de `manifest.knowledge_base_id` (manifest.schema.json): UUID en
minúsculas. `id_scheme.is_valid_uuid` también acepta mayúsculas, que el
schema rechazaría; se exigen ambas cosas."""


def _uuid_valido(valor: Any) -> bool:
    return isinstance(valor, str) and bool(_UUID_CONTRATO.match(valor)) and k.is_valid_uuid(valor)


_ZIP_FECHA = (1980, 1, 1, 0, 0, 0)
_ZIP_NIVEL = 6

DATA_FILES = (
    "access_hierarchy.json", "acceptance_cases.jsonl", "chunks.jsonl", "conversational_bundle.json",
    "embedding_spaces.json", "evidence.jsonl", "indexes.json", "media.jsonl", "metadata_schema.json",
    "source_metadata.jsonl", "sources.jsonl",
)
"""11 archivos de datos + manifest.json + checksums.json = 13 archivos internos."""


# --------------------------------------------------------------- utilidades

def _iso_datetime(valor: Any) -> str:
    """Fecha-hora RFC 3339 en UTC con offset (`...+00:00`). RAG Studio guarda
    UTC (UTCDateTime); un valor sin zona se interpreta como UTC."""
    if isinstance(valor, datetime):
        dt = valor
    else:
        dt = datetime.fromisoformat(str(valor).strip().replace(" ", "T"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _iso_date(valor: Any) -> Optional[str]:
    if valor in (None, ""):
        return None
    return date.fromisoformat(str(valor)[:10]).isoformat()


def _json(texto: Any, defecto: Any) -> Any:
    if texto in (None, ""):
        return defecto
    return json.loads(texto)


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _sin_duplicados(tipo: str, pares: list[tuple[str, str]]) -> None:
    """pares: (id_portable, origen). Lanza PortableIdentityCollisionError."""
    vistos: dict[str, list[str]] = defaultdict(list)
    for pid, origen in pares:
        vistos[pid].append(origen)
    colisiones = {pid: origenes for pid, origenes in vistos.items() if len(origenes) > 1}
    if colisiones:
        raise PortableIdentityCollisionError(tipo, colisiones)


def package_id_for(knowledge_base_id: str, snapshot_id: str, tenant: str) -> str:
    """Convención NO normativa de RAG Studio (Alcance §5): primeros 32 hex del
    SHA-256 de la serialización RFC 8785 de estos cinco campos."""
    datos = {
        "knowledge_base_id": knowledge_base_id, "snapshot_id": snapshot_id, "tenant": tenant,
        "schema_version": CONTRACT_SCHEMA_VERSION, "exporter_version": EXPORTER_VERSION,
    }
    return "urn:nexom:package:" + k.sha256_hex(rfc8785.dumps(datos))[:32]


# ------------------------------------------------------- lectura de la copia

class _Lectura:
    """Datos crudos leídos de la COPIA temporal del project.db de la instantánea."""

    def __init__(self, con: sqlite3.Connection, project_id: str):
        con.row_factory = sqlite3.Row
        self.con = con
        self.project_id = project_id

    def filas(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        return list(self.con.execute(sql, args))

    def columnas(self, tabla: str) -> set[str]:
        return {r[1] for r in self.con.execute(f"PRAGMA table_info({tabla})")}


class NexomKnowledgePackageExporter(KnowledgePackageExporter):
    def __init__(self, conformance: Optional[KnowledgePackageConformanceValidator] = None):
        """RAG-INC-01c: la compuerta de conformidad es obligatoria. Sin una
        explícita se usa la del contrato v1.0.0 vendorizado."""
        if conformance is None:
            from .nkp_conformance import ContractV1ConformanceValidator

            conformance = ContractV1ConformanceValidator()
        self._conformance = conformance

    def export(self, snapshot: SnapshotDescriptor, tenant: str, output_dir: str) -> KnowledgePackageExportResult:
        carpeta = Path(snapshot.snapshot_dir)
        db_instantanea = carpeta / "project.db"
        if not carpeta.is_dir():
            raise SnapshotDirectoryMissingError(snapshot.id, snapshot.version, snapshot.snapshot_dir)
        if not db_instantanea.is_file():
            raise SnapshotDirectoryMissingError(
                snapshot.id, snapshot.version, snapshot.snapshot_dir, "la carpeta no contiene project.db",
            )

        temporal = Path(tempfile.mkdtemp(prefix="nkp-lectura-"))
        try:
            copia = temporal / "project.db"
            shutil.copy2(db_instantanea, copia)
            wal = carpeta / "project.db-wal"
            if wal.is_file():
                shutil.copy2(wal, temporal / "project.db-wal")
            con = sqlite3.connect(copia)
            try:
                archivos, manifest = self._construir(_Lectura(con, snapshot.project_id), snapshot, tenant, carpeta)
            finally:
                con.close()
        finally:
            shutil.rmtree(temporal, ignore_errors=True)
        return self._publicar(archivos, manifest, tenant, Path(output_dir))

    # ------------------------------------------------------------ construcción

    def _construir(
        self, lec: _Lectura, snapshot: SnapshotDescriptor, tenant: str, carpeta: Path,
    ) -> tuple[dict[str, bytes], dict]:
        # --- proyecto e identidades persistentes
        if "knowledge_base_id" not in lec.columnas("project") or "lineage_id" not in lec.columnas("source"):
            raise SnapshotInconsistentError(
                "La instantánea es anterior a las identidades persistentes (migración 0021): no tiene "
                "knowledge_base_id/lineage_id. Publique una instantánea nueva."
            )
        proyectos = lec.filas("SELECT id, knowledge_base_id, updated_at FROM project")
        if len(proyectos) != 1 or proyectos[0]["id"] != snapshot.project_id:
            raise SnapshotInconsistentError(
                f"El project.db de la instantánea no corresponde al proyecto registrado "
                f"({snapshot.project_id!r}): contiene {[p['id'] for p in proyectos]!r}."
            )
        proyecto = proyectos[0]
        kb = proyecto["knowledge_base_id"]
        if not _uuid_valido(kb) or not k.is_valid_knowledge_base_id(kb):
            raise MissingIdentityError(f"knowledge_base_id ausente o inválido ({kb!r}).")
        pid = snapshot.project_id

        fuentes = lec.filas(
            "SELECT id, title, source_type, owner_area, access_level, language, content_hash, validation_status, "
            "valid_from, valid_to, source_authority, supersedes_source_id, lineage_id, document_type_code, "
            "created_at, updated_at FROM source WHERE project_id = ? ORDER BY id", pid,
        )
        malas = [f["id"] for f in fuentes if not _uuid_valido(f["lineage_id"])]
        if malas:
            raise MissingIdentityError(f"lineage_id ausente o inválido en {len(malas)} fuente(s).", malas)

        # --- precondición INC01-R1: huella de contenido
        sin_huella = [
            (f["id"], f["title"]) for f in fuentes
            if f["source_type"] not in _NON_FILE_VALUES and (f["content_hash"] is None or f["content_hash"] == "")
        ]
        if sin_huella:
            raise MissingContentHashError(sin_huella)

        indices = lec.filas(
            "SELECT embedding_provider, embedding_model, dimensions, points_count, updated_at "
            "FROM index_info WHERE project_id = ?", pid,
        )
        if not indices:
            raise ContractConstraintError("La instantánea no tiene índice (index_info): no se puede declarar el espacio de embeddings.")
        indice = indices[0]

        # --- fuentes
        ids_fuente: dict[str, str] = {}
        registros_fuente: list[dict] = []
        for f in fuentes:
            updated = _iso_datetime(f["updated_at"])
            vkey = k.source_version_key(f["content_hash"], f["title"], f["source_type"], updated)
            ids_fuente[f["id"]] = k.portable_source_id(f["lineage_id"], vkey)
        _sin_duplicados("source.id", [(ids_fuente[f["id"]], f["id"]) for f in fuentes])
        for f in fuentes:
            sup = f["supersedes_source_id"]
            if sup and sup not in ids_fuente:
                raise BrokenReferenceError(
                    f"La fuente {f['id']!r} sustituye a {sup!r}, que no está en la instantánea."
                )
            autoridad = f["source_authority"]
            if autoridad is not None and int(autoridad) < 1:
                raise ContractConstraintError(f"source_authority={autoridad} de la fuente {f['id']!r}: el contrato exige >= 1 o null.")
            registros_fuente.append({
                "id": ids_fuente[f["id"]], "logical_id": k.portable_source_logical_id(f["lineage_id"]),
                "origin_id": f["id"], "title": f["title"], "source_type": f["source_type"],
                "owner_area": f["owner_area"], "access_level": f["access_level"], "language": f["language"],
                "content_hash": f["content_hash"], "validation_status": f["validation_status"],
                "valid_from": _iso_date(f["valid_from"]), "valid_to": _iso_date(f["valid_to"]),
                "source_authority": autoridad, "supersedes_source_id": ids_fuente[sup] if sup else None,
                "document_type_code": f["document_type_code"],
                "created_at": _iso_datetime(f["created_at"]), "updated_at": _iso_datetime(f["updated_at"]),
                "original_included": False, "original_omission_reason": "not_applicable_profile_core",
                "original_media_type": None, "original_checksum": None, "original_relative_path": None,
            })

        # --- esquema de metadatos (esquema activo de mayor versión)
        esquemas = lec.filas(
            "SELECT id, version FROM metadata_schema WHERE project_id = ? AND is_active = 1 ORDER BY version DESC", pid,
        )
        catalogos = lec.filas("SELECT id, name FROM catalog WHERE project_id = ? ORDER BY name, id", pid)
        cat_urn = {c["id"]: k.portable_catalog_id(kb, c["name"]) for c in catalogos}
        _sin_duplicados("catalog.id", [(cat_urn[c["id"]], f"{c['name']} ({c['id']})") for c in catalogos])
        registros_catalogo = []
        codigos_catalogo: dict[str, set[str]] = {}
        for c in catalogos:
            entradas = lec.filas(
                "SELECT id, value_code, label, parent_entry_id FROM catalog_entry WHERE catalog_id = ? ORDER BY value_code, id",
                c["id"],
            )
            codigo_por_id = {e["id"]: e["value_code"] for e in entradas}
            lista = []
            for e in entradas:
                padre = e["parent_entry_id"]
                if padre and padre not in codigo_por_id:
                    raise BrokenReferenceError(
                        f"La entrada {e['value_code']!r} del catálogo {c['name']!r} apunta a un padre inexistente."
                    )
                lista.append({"value_code": e["value_code"], "label": e["label"],
                              "parent_entry_code": codigo_por_id[padre] if padre else None})
            codigos_catalogo[c["id"]] = {e["value_code"] for e in entradas}
            registros_catalogo.append({"id": cat_urn[c["id"]], "name": c["name"], "entries": lista})

        campos: list[sqlite3.Row] = []
        version_local = 1
        if esquemas:
            version_local = int(esquemas[0]["version"])
            campos = lec.filas(
                "SELECT field_id, display_name, data_type, required, filterable, multiple, inherited_by_chunks, "
                "catalog_id FROM field_definition WHERE schema_id = ? ORDER BY field_id", esquemas[0]["id"],
            )
        campo_urn = {c["field_id"]: k.portable_field_definition_id(kb, c["field_id"]) for c in campos}
        campo_por_codigo = {c["field_id"]: c for c in campos}
        registros_campo = []
        for c in campos:
            if c["catalog_id"] and c["catalog_id"] not in cat_urn:
                raise BrokenReferenceError(f"El campo {c['field_id']!r} referencia un catálogo inexistente.")
            registros_campo.append({
                "id": campo_urn[c["field_id"]], "field_id": c["field_id"], "display_name": c["display_name"],
                "data_type": c["data_type"], "required": bool(c["required"]), "filterable": bool(c["filterable"]),
                "multiple": bool(c["multiple"]), "inherited_by_chunks": bool(c["inherited_by_chunks"]),
                "catalog_id": cat_urn[c["catalog_id"]] if c["catalog_id"] else None,
            })
        metadata_schema = {
            "schema_version_local": version_local, "knowledge_base_id": kb,
            "fields": registros_campo, "catalogs": registros_catalogo,
        }

        # --- valores de metadatos por fuente
        registros_valor = []
        if fuentes:
            marcas = ",".join("?" * len(fuentes))
            valores = lec.filas(
                f"SELECT source_id, field_id, value, created_at FROM source_metadata_value "
                f"WHERE source_id IN ({marcas}) ORDER BY source_id, field_id", *[f["id"] for f in fuentes],
            )
            for v in valores:
                campo = campo_por_codigo.get(v["field_id"])
                if campo is None:
                    raise BrokenReferenceError(
                        f"La fuente {v['source_id']!r} tiene un valor del campo {v['field_id']!r}, que no existe "
                        f"en el esquema de metadatos activo."
                    )
                lista = v["value"].split("|") if campo["multiple"] else [v["value"]]
                if campo["catalog_id"]:
                    invalidos = [x for x in lista if x not in codigos_catalogo[campo["catalog_id"]]]
                    if invalidos:
                        raise BrokenReferenceError(
                            f"La fuente {v['source_id']!r}, campo {v['field_id']!r}: valores fuera del catálogo {invalidos!r}."
                        )
                sid = ids_fuente[v["source_id"]]
                fid = campo_urn[v["field_id"]]
                registros_valor.append({
                    "id": f"{sid}:{fid}", "source_id": sid, "field_definition_id": fid, "field_code": v["field_id"],
                    "value": lista, "created_at": _iso_datetime(v["created_at"]),
                })
        _sin_duplicados("source_metadata.id", [(r["id"], r["field_code"]) for r in registros_valor])

        # --- chunks, evidencia y media
        chunks = lec.filas(
            "SELECT id, source_id, chunk_index, text, token_count, section_title, page_start, page_end, chunk_type, "
            "previous_chunk_id, next_chunk_id, parent_chunk_id, structured_content, semantic_summary, "
            "inherited_metadata, created_at, image_relative_path FROM chunk WHERE project_id = ? ORDER BY source_id, chunk_index, id",
            pid,
        )
        ids_chunk: dict[str, str] = {}
        for c in chunks:
            if c["source_id"] not in ids_fuente:
                raise BrokenReferenceError(f"El chunk {c['id']!r} pertenece a una fuente que no está en la instantánea.")
            if c["chunk_type"] != "imagen" and not (c["text"] or ""):
                raise ContractConstraintError(
                    f"El chunk {c['id']!r} ({c['chunk_type']}) tiene texto vacío: el contrato exige texto en todo chunk no imagen."
                )
            ids_chunk[c["id"]] = k.portable_chunk_id(ids_fuente[c["source_id"]], int(c["chunk_index"]), c["text"] or "")
        _sin_duplicados("chunk.id", [(ids_chunk[c["id"]], c["id"]) for c in chunks])

        fuente_por_portable = {r["id"]: r for r in registros_fuente}
        registros_chunk: list[dict[str, Any]] = []
        registros_evidencia: list[dict[str, Any]] = []
        registros_media: list[dict[str, Any]] = []
        for c in chunks:
            enlaces: dict[str, Optional[str]] = {}
            for enlace in ("previous_chunk_id", "next_chunk_id", "parent_chunk_id"):
                destino = c[enlace]
                if destino and destino not in ids_chunk:
                    raise BrokenReferenceError(f"El chunk {c['id']!r} tiene {enlace}={destino!r}, que no existe.")
                enlaces[enlace] = ids_chunk[destino] if destino else None
            heredados: dict[str, str] = {}
            for codigo, valor in (_json(c["inherited_metadata"], {}) or {}).items():
                if codigo not in campo_urn:
                    raise BrokenReferenceError(
                        f"El chunk {c['id']!r} hereda el campo {codigo!r}, que no existe en el esquema de metadatos activo."
                    )
                heredados[campo_urn[codigo]] = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
            estructurado = _json(c["structured_content"], None)
            if estructurado is not None and not isinstance(estructurado, dict):
                raise ContractConstraintError(f"structured_content del chunk {c['id']!r} no es un objeto JSON.")
            pid_chunk = ids_chunk[c["id"]]
            sid = ids_fuente[c["source_id"]]
            registro = {
                "id": pid_chunk, "source_id": sid, "chunk_index": int(c["chunk_index"]), "text": c["text"] or "",
                "token_count": int(c["token_count"]), "chunk_type": c["chunk_type"],
                "section_title": c["section_title"], "page_start": c["page_start"], "page_end": c["page_end"],
                **enlaces, "structured_content": estructurado, "semantic_summary": c["semantic_summary"],
                "inherited_metadata": heredados, "created_at": _iso_datetime(c["created_at"]),
            }
            if c["chunk_type"] == "imagen":
                nombre = Path(str(c["image_relative_path"] or "").replace("\\", "/")).name
                binario = carpeta / "sources" / "original" / nombre if nombre else None
                if binario is None or not binario.is_file():
                    raise BrokenReferenceError(
                        f"El chunk de imagen {c['id']!r} no tiene su archivo en la instantánea "
                        f"(sources/original/{nombre or '?'})."
                    )
                ruta = f"assets/images/{nombre}"
                checksum = "sha256:" + _sha256_archivo(binario)
                registro["image_relative_path"] = ruta
                registros_media.append({
                    "id": k.portable_media_id(pid_chunk, checksum), "media_type": "image", "chunk_id": pid_chunk,
                    "source_id": sid, "relative_path": ruta, "checksum": checksum, "included_in_package": False,
                    "note": "Perfil CORE: solo descriptor. El binario no viaja en el paquete.",
                })
            elif c["chunk_type"] != "padre":
                fuente = fuente_por_portable[sid]
                registros_evidencia.append({
                    "id": k.portable_evidence_id(pid_chunk, "citation_anchor"), "evidence_kind": "citation_anchor",
                    "derivation_method": "derived_from_chunk_source", "verification_status": "derived",
                    "source_id": sid, "chunk_id": pid_chunk, "page_range": [c["page_start"], c["page_end"]],
                    "section_title": c["section_title"], "content_hash": k.sha256_hex((c["text"] or "").encode("utf-8")),
                    "source_authority": fuente["source_authority"], "source_valid_from": fuente["valid_from"],
                    "source_valid_to": fuente["valid_to"],
                })
            registros_chunk.append(registro)
        _sin_duplicados("evidence.id", [(e["id"], e["chunk_id"]) for e in registros_evidencia])
        _sin_duplicados("media.id", [(m["id"], m["chunk_id"]) for m in registros_media])
        _sin_duplicados("media.relative_path", [(m["relative_path"], m["chunk_id"]) for m in registros_media])

        # --- artefactos conversacionales
        bundle = self._bundle(lec, pid, kb)

        # --- embeddings, índices y jerarquía de acceso
        espacio_id = f"text_semantic_{int(indice['dimensions'])}"
        tipos_texto = sorted({c["chunk_type"] for c in chunks if c["chunk_type"] not in _NO_INDEXABLES})
        embedding_spaces = [{
            "id": espacio_id, "modality": "text", "provider": indice["embedding_provider"],
            "model": indice["embedding_model"], "revision": None, "dimensions": int(indice["dimensions"]),
            "normalization": "unknown_not_verified",
            "preprocessing": _PREFIJOS_POR_MODELO.get(indice["embedding_model"]),
            "distance_metric": "cosine", "dtype": "float32", "fingerprint": None,
        }]
        indexes = [{
            "id": f"chunks_{espacio_id}", "embedding_space_id": espacio_id, "index_type": "flat_cosine",
            "points_count": int(indice["points_count"]), "covers_chunk_types": tipos_texto,
            "updated_at": _iso_datetime(indice["updated_at"]),
        }]
        access_hierarchy = {
            "order": [nivel.value for nivel in sorted(AccessLevel, key=lambda n: _ACCESS_LEVEL_RANK[n])],
            "rule": _ACCESS_RULE,
        }

        archivos: dict[str, bytes] = {
            "sources.jsonl": k.canonical_jsonl_bytes(registros_fuente, sort_key="id"),
            "chunks.jsonl": k.canonical_jsonl_bytes(registros_chunk, sort_key="id"),
            "source_metadata.jsonl": k.canonical_jsonl_bytes(registros_valor, sort_key="id"),
            "metadata_schema.json": k.canonical_json_bytes(metadata_schema),
            "evidence.jsonl": k.canonical_jsonl_bytes(registros_evidencia, sort_key="id"),
            "media.jsonl": k.canonical_jsonl_bytes(registros_media, sort_key="id"),
            "conversational_bundle.json": k.canonical_json_bytes(bundle),
            "embedding_spaces.json": k.canonical_json_bytes(embedding_spaces),
            "indexes.json": k.canonical_json_bytes(indexes),
            # Vacío en RAG-INC-01 (decisión INC01-D5 del Alcance firmado).
            "acceptance_cases.jsonl": k.canonical_jsonl_bytes([], sort_key="case_id"),
            "access_hierarchy.json": k.canonical_json_bytes(access_hierarchy),
        }
        if set(archivos) != set(DATA_FILES):  # pragma: no cover - defensa ante cambios futuros
            raise ContractConstraintError("Conjunto de archivos de datos inesperado.")

        omisiones = []
        if registros_media:
            omisiones.append({"code": "MEDIA_BINARIES_NOT_INCLUDED", "description":
                              f"Perfil CORE: media.jsonl declara {len(registros_media)} imagen(es) pero los binarios no viajan en el paquete."})
        if registros_fuente:
            omisiones.append({"code": "ORIGINALS_NOT_INCLUDED", "description":
                              "Perfil CORE: ninguna fuente incluye su archivo original (original_included=false en todas)."})
        omisiones.append({"code": "VECTORS_NOT_INCLUDED", "description":
                          "v1.0 no transporta vectores en perfil CORE; el consumidor reindexa desde chunks.jsonl."})
        if registros_evidencia:
            omisiones.append({"code": "EVIDENCE_NOT_VERIFIED", "description":
                              f"Los {len(registros_evidencia)} registros de evidence.jsonl tienen verification_status=derived: "
                              "RAG Studio no tiene hoy verificación editorial de evidencia."})

        manifest = {
            "package_id": package_id_for(kb, snapshot.id, tenant),
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "knowledge_version": str(snapshot.version),
            "created_at": _iso_datetime(snapshot.created_at),
            "source_system": "rag-studio",
            "exporter_version": EXPORTER_VERSION,
            "tenant": tenant,
            "knowledge_base_id": kb,
            "project_id_origin": pid,
            "project_revision": _iso_datetime(proyecto["updated_at"]),
            "snapshot_id": snapshot.id,
            "parent_package_id": None,
            "profile": PROFILE_CORE,
            "counts": {
                "sources": len(registros_fuente), "chunks": len(registros_chunk),
                "evidence": len(registros_evidencia), "media": len(registros_media),
                "intents": len(bundle["intents"]), "guardrail_rules": len(bundle["guardrail_rules"]),
                "acceptance_cases": 0,
            },
            "files": sorted([*DATA_FILES, "manifest.json", "checksums.json"]),
            "capabilities": {
                "text_retrieval": bool(tipos_texto),
                "structured_retrieval": any(r["structured_content"] is not None for r in registros_chunk),
                "image_retrieval": False,
            },
            "omissions": omisiones,
        }
        archivos["manifest.json"] = k.canonical_json_bytes(manifest)
        return archivos, manifest

    def _bundle(self, lec: _Lectura, pid: str, kb: str) -> dict:
        variables = lec.filas("SELECT code, label FROM conversational_variable WHERE project_id = ? ORDER BY code", pid)
        canales = lec.filas("SELECT code, medium, summary_template FROM channeling_scheme WHERE project_id = ? ORDER BY code", pid)
        intents = lec.filas(
            "SELECT name, description, positive_examples, negative_examples, priority, risk_level, required_variables, "
            "optional_variables, clarifying_questions, response_rule, fallback_channeling_code, resolution_mode, active, "
            "created_at, updated_at FROM intent WHERE project_id = ? ORDER BY name", pid,
        )
        reglas = lec.filas(
            "SELECT name, rule_type, conditions, action, priority, active, created_at, updated_at "
            "FROM guardrail_rule WHERE project_id = ? ORDER BY name", pid,
        )
        var_urn = {v["code"]: k.portable_variable_id(kb, v["code"]) for v in variables}
        can_urn = {c["code"]: k.portable_channeling_id(kb, c["code"]) for c in canales}
        _sin_duplicados("conversational_variable.id", [(var_urn[v["code"]], v["code"]) for v in variables])
        _sin_duplicados("channeling_scheme.id", [(can_urn[c["code"]], c["code"]) for c in canales])
        _sin_duplicados("intent.id", [(k.portable_intent_id(kb, i["name"]), i["name"]) for i in intents])
        _sin_duplicados("guardrail.id", [(k.portable_guardrail_id(kb, r["name"]), r["name"]) for r in reglas])

        def variable(intent: str, codigo: str) -> str:
            if codigo not in var_urn:
                raise BrokenReferenceError(f"La intención {intent!r} usa la variable {codigo!r}, que no existe.")
            return var_urn[codigo]

        for v in variables:
            if not (v["label"] or "").strip():
                raise ContractConstraintError(f"La variable {v['code']!r} no tiene etiqueta (display_name es obligatorio).")
        registros_intent = []
        for i in intents:
            respaldo = i["fallback_channeling_code"]
            if respaldo and respaldo not in can_urn:
                raise BrokenReferenceError(f"La intención {i['name']!r} canaliza a {respaldo!r}, que no existe.")
            registros_intent.append({
                "id": k.portable_intent_id(kb, i["name"]), "name": i["name"], "description": i["description"] or "",
                "positive_examples": _json(i["positive_examples"], []), "negative_examples": _json(i["negative_examples"], []),
                "priority": int(i["priority"]), "risk_level": i["risk_level"],
                "required_variables": [variable(i["name"], c) for c in _json(i["required_variables"], [])],
                "optional_variables": [variable(i["name"], c) for c in _json(i["optional_variables"], [])],
                "clarifying_questions": {variable(i["name"], c): q for c, q in _json(i["clarifying_questions"], {}).items()},
                "response_rule": i["response_rule"] or "",
                "fallback_channeling_code": can_urn[respaldo] if respaldo else None,
                "resolution_mode": i["resolution_mode"], "active": bool(i["active"]),
                "created_at": _iso_datetime(i["created_at"]), "updated_at": _iso_datetime(i["updated_at"]),
            })
        registros_regla = [{
            "id": k.portable_guardrail_id(kb, r["name"]), "name": r["name"], "rule_type": r["rule_type"],
            "conditions": [{"field": c["field"], "operator": c["operator"], "value": str(c["value"])}
                           for c in _json(r["conditions"], [])],
            "action": r["action"], "priority": int(r["priority"]), "active": bool(r["active"]),
            "created_at": _iso_datetime(r["created_at"]), "updated_at": _iso_datetime(r["updated_at"]),
        } for r in reglas]
        return {
            "intents": sorted(registros_intent, key=lambda x: x["id"]),
            "guardrail_rules": sorted(registros_regla, key=lambda x: x["id"]),
            "conversational_variables": sorted(
                [{"id": var_urn[v["code"]], "code": v["code"], "display_name": v["label"]} for v in variables],
                key=lambda x: x["id"]),
            "channeling_schemes": sorted(
                [{"id": can_urn[c["code"]], "code": c["code"], "medium": c["medium"],
                  "summary_template": c["summary_template"] or ""} for c in canales],
                key=lambda x: x["id"]),
        }

    # ------------------------------------------------------------ publicación

    def _publicar(self, archivos: dict[str, bytes], manifest: dict, tenant: str, salida: Path) -> KnowledgePackageExportResult:
        nombre = "nexom-knowledge-package-" + manifest["package_id"].rsplit(":", 1)[-1]
        final_zip = salida / f"{nombre}.zip"
        final_digest = salida / f"{nombre}.content.sha256"
        for destino in (final_zip, final_digest):
            if destino.exists():
                raise OutputExistsError(str(destino))
        salida.mkdir(parents=True, exist_ok=True)
        staging = salida / f".nkp-staging-{uuid.uuid4().hex}"
        publicados: list[Path] = []
        try:
            staging.mkdir()
            hashes = {n: k.sha256_hex(datos) for n, datos in sorted(archivos.items())}
            checksums = {"algorithm": "sha256", "canonicalization": "rfc8785", "files": hashes}
            checksums_bytes = k.canonical_json_bytes(checksums)
            checksums_hash = k.sha256_hex(checksums_bytes)
            digest = k.content_digest(hashes, checksums_hash)
            contenido = {**archivos, "checksums.json": checksums_bytes}
            if sorted(contenido) != manifest["files"]:
                raise ContractConstraintError("Los archivos generados no coinciden con manifest.files.")

            zip_staging = staging / f"{nombre}.zip"
            self._escribir_zip(zip_staging, contenido)
            self._verificar_zip(zip_staging, contenido)
            digest_staging = staging / f"{nombre}.content.sha256"
            digest_staging.write_bytes((digest + "\n").encode("ascii"))

            # RAG-INC-01c: compuerta de conformidad sobre el ZIP y el sidecar
            # tal como se van a publicar. FAIL ⇒ no se publica nada.
            conformidad: ConformanceReport = self._conformance.validate(str(zip_staging), str(digest_staging))
            if not conformidad.passed:
                logger.error("Exportación NKP rechazada por la compuerta de conformidad:\n%s", conformidad.summary())
                raise ContractConformanceError(conformidad)

            # RAG-INC-01d: el SHA-256 del ZIP se obtiene del archivo en staging,
            # el mismo que se publica sin modificación. Nunca se relee el ZIP
            # publicado: en un sistema de archivos montado (FUSE) esa relectura
            # falló de forma transitoria con los archivos ya publicados.
            zip_sha256 = _sha256_archivo(zip_staging)

            for origen, destino in ((zip_staging, final_zip), (digest_staging, final_digest)):
                self._publicar_sin_sobrescribir(origen, destino)
                publicados.append(destino)
        except BaseException:
            for ruta in publicados:
                try:
                    ruta.unlink()
                except OSError:  # pragma: no cover - se informa en el log
                    logger.warning("No se pudo retirar %s tras un fallo de exportación.", ruta)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return KnowledgePackageExportResult(
            package_id=manifest["package_id"], knowledge_base_id=manifest["knowledge_base_id"],
            snapshot_id=manifest["snapshot_id"], tenant=tenant, zip_path=str(final_zip),
            content_digest_path=str(final_digest), content_digest=digest, checksums_json_hash=checksums_hash,
            zip_sha256=zip_sha256, counts=dict(manifest["counts"]), conformance=conformidad,
        )

    @staticmethod
    def _escribir_zip(destino: Path, contenido: dict[str, bytes]) -> None:
        """ZIP determinista: entradas ordenadas, fecha fija, permisos y sistema
        de origen fijos, compresión DEFLATE nivel fijo."""
        with zipfile.ZipFile(destino, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=_ZIP_NIVEL) as zf:
            for nombre in sorted(contenido):
                info = zipfile.ZipInfo(nombre, date_time=_ZIP_FECHA)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100644 & 0xFFFF) << 16
                zf.writestr(info, contenido[nombre], compress_type=zipfile.ZIP_DEFLATED, compresslevel=_ZIP_NIVEL)

    @staticmethod
    def _verificar_zip(ruta: Path, contenido: dict[str, bytes]) -> None:
        with zipfile.ZipFile(ruta) as zf:
            if zf.testzip() is not None or sorted(zf.namelist()) != sorted(contenido):
                raise ContractConstraintError("El ZIP generado no coincide con el contenido previsto.")
            for nombre, datos in contenido.items():
                if zf.read(nombre) != datos:
                    raise ContractConstraintError(f"El ZIP generado difiere en {nombre}.")

    @staticmethod
    def _publicar_sin_sobrescribir(origen: Path, destino: Path) -> None:
        """Publica `origen` (staging) como `destino` sin sobrescribir nunca un
        archivo existente. Si falla, no deja `destino`.

        1. `os.link`: crea el nombre final de forma atómica y falla si ya
           existe (el staging está en la misma carpeta de salida, así que es
           el mismo sistema de archivos).
        2. Sin enlaces duros: se reserva el nombre en exclusiva (`open(..., "x")`)
           y se reemplaza con `os.replace`, que es un rename atómico. Si el
           reemplazo falla, se retira la reserva vacía.
        La atomicidad es por archivo. La pareja ZIP + sidecar la garantiza
        `_publicar`, que retira el ZIP si falla el sidecar."""
        try:
            os.link(origen, destino)  # atómico y falla si el destino ya existe
            return
        except FileExistsError:
            raise OutputExistsError(str(destino)) from None
        except OSError:
            pass  # sin enlaces duros: alternativa con reserva exclusiva
        try:
            with open(destino, "xb"):
                pass
        except FileExistsError:
            raise OutputExistsError(str(destino)) from None
        try:
            os.replace(origen, destino)
        except BaseException:
            try:
                destino.unlink()
            except OSError:  # pragma: no cover - se informa en el log
                logger.warning("No se pudo retirar la reserva %s tras un fallo de publicación.", destino)
            raise
