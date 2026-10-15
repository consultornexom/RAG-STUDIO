"""Casos negativos de conformidad NKP v1.0.0 (RAG-INC-01c).

Cada caso parte de una copia de un paquete VÁLIDO generado por el exportador
y le introduce un único defecto. Cuando el defecto no es el checksum mismo,
se recalcula `checksums.json` (y el sidecar `content_digest`) con el
`id_scheme.py` firmado, para que el defecto probado sea el único presente
(misma metodología de aislamiento que la suite negativa firmada)."""
from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Callable

from contracts.nexom_knowledge_package import load_id_scheme

k = load_id_scheme()
SIDECAR = "paquete.content.sha256"


def leer_jsonl(d: Path, nombre: str) -> list[dict]:
    return [json.loads(x) for x in (d / nombre).read_text(encoding="utf-8").splitlines() if x.strip()]


def escribir_jsonl(d: Path, nombre: str, registros: list[dict], clave: str = "id") -> None:
    (d / nombre).write_bytes(k.canonical_jsonl_bytes(registros, sort_key=clave))


def leer_json(d: Path, nombre: str):
    return json.loads((d / nombre).read_text(encoding="utf-8"))


def escribir_json(d: Path, nombre: str, obj) -> None:
    (d / nombre).write_bytes(k.canonical_json_bytes(obj))


def recalcular(d: Path) -> None:
    """Recalcula checksums.json y el sidecar content_digest del directorio."""
    manifest = leer_json(d, "manifest.json")
    archivos = {}
    for nombre in manifest["files"]:
        if nombre == "checksums.json" or not (d / nombre).exists():
            continue
        if nombre.endswith(".jsonl"):
            clave = "case_id" if nombre == "acceptance_cases.jsonl" else "id"
            archivos[nombre] = k.sha256_hex(k.canonical_jsonl_bytes(leer_jsonl(d, nombre), sort_key=clave))
        else:
            archivos[nombre] = k.sha256_hex(k.canonical_json_bytes(leer_json(d, nombre)))
    checksums = {"algorithm": "sha256", "canonicalization": "rfc8785", "files": archivos}
    datos = k.canonical_json_bytes(checksums)
    (d / "checksums.json").write_bytes(datos)
    (d.parent / f"{d.name}.{SIDECAR}").write_text(k.content_digest(archivos, k.sha256_hex(datos)) + "\n")


def preparar(zip_valido: Path, destino: Path) -> Path:
    if destino.exists():
        shutil.rmtree(destino)
    with zipfile.ZipFile(zip_valido) as zf:
        zf.extractall(destino)
    recalcular(destino)  # sidecar del directorio base
    return destino


def sidecar(d: Path) -> Path:
    return d.parent / f"{d.name}.{SIDECAR}"


# ------------------------------------------------------------- mutaciones

def schema_roto(d: Path) -> None:
    chunks = leer_jsonl(d, "chunks.jsonl")
    chunks[0]["chunk_type"] = "tipo_inexistente"
    escribir_jsonl(d, "chunks.jsonl", chunks)
    recalcular(d)


def manifest_invalido(d: Path) -> None:
    m = leer_json(d, "manifest.json")
    m["package_id"] = "paquete-sin-formato-urn"
    escribir_json(d, "manifest.json", m)
    recalcular(d)


def checksum_roto(d: Path) -> None:
    fuentes = leer_jsonl(d, "sources.jsonl")
    fuentes[0]["title"] += " (alterado)"
    escribir_jsonl(d, "sources.jsonl", fuentes)  # sin recalcular checksums


def content_digest_roto(d: Path) -> None:
    sidecar(d).write_text("0" * 64 + "\n")


def source_id_incorrecto(d: Path) -> None:
    """Sustituye el UUID de versión de una fuente por uno arbitrario y lo
    propaga de forma consistente a todo el paquete (caso de la auditoría rc3.1)."""
    viejo = leer_jsonl(d, "sources.jsonl")[0]["id"].rsplit(":", 1)[-1]
    nuevo = str(uuid.uuid4())
    for archivo in d.iterdir():
        if archivo.is_file() and archivo.name != "checksums.json":
            archivo.write_text(archivo.read_text(encoding="utf-8").replace(viejo, nuevo), encoding="utf-8")
    recalcular(d)


def chunk_id_incorrecto(d: Path) -> None:
    chunks = leer_jsonl(d, "chunks.jsonl")
    chunks[0]["text"] += " modificado"
    escribir_jsonl(d, "chunks.jsonl", chunks)
    recalcular(d)


def id_duplicado(d: Path) -> None:
    chunks = leer_jsonl(d, "chunks.jsonl")
    (d / "chunks.jsonl").write_bytes(
        k.canonical_jsonl_bytes(chunks, sort_key="id") + k.canonical_jsonl_bytes([chunks[0]], sort_key="id"))
    m = leer_json(d, "manifest.json")
    m["counts"]["chunks"] = len(chunks) + 1
    escribir_json(d, "manifest.json", m)
    recalcular(d)


def archivo_requerido_faltante(d: Path) -> None:
    (d / "access_hierarchy.json").unlink()
    m = leer_json(d, "manifest.json")
    m["files"] = [f for f in m["files"] if f != "access_hierarchy.json"]
    escribir_json(d, "manifest.json", m)
    recalcular(d)


def archivo_inesperado(d: Path) -> None:
    (d / "notas.txt").write_text("archivo no declarado")


def referencia_rota(d: Path) -> None:
    chunks = leer_jsonl(d, "chunks.jsonl")
    fuente = chunks[0]["id"].split(":")[3]
    chunks[0]["previous_chunk_id"] = f"urn:nexom:chunk:{fuente}:{'f' * 64}"
    escribir_jsonl(d, "chunks.jsonl", chunks)
    recalcular(d)


def cardinalidad_incorrecta(d: Path) -> None:
    m = leer_json(d, "manifest.json")
    m["counts"]["sources"] += 7
    escribir_json(d, "manifest.json", m)
    recalcular(d)


def metadata_schema_invalido(d: Path) -> None:
    ms = leer_json(d, "metadata_schema.json")
    ms["fields"][0]["catalog_id"] = f"urn:nexom:catalog:{uuid.uuid4()}"
    escribir_json(d, "metadata_schema.json", ms)
    recalcular(d)


def embeddings_invalidos(d: Path) -> None:
    espacios = leer_json(d, "embedding_spaces.json")
    espacios[0]["dimensions"] = 0
    escribir_json(d, "embedding_spaces.json", espacios)
    recalcular(d)


def indice_sin_espacio(d: Path) -> None:
    indices = leer_json(d, "indexes.json")
    indices[0]["embedding_space_id"] = "espacio_inexistente"
    escribir_json(d, "indexes.json", indices)
    recalcular(d)


def access_hierarchy_invalida(d: Path) -> None:
    escribir_json(d, "access_hierarchy.json", {
        "order": ["publico", "interno", "confidencial"], "rule": leer_json(d, "access_hierarchy.json")["rule"]})
    recalcular(d)


def bundle_invalido(d: Path) -> None:
    b = leer_json(d, "conversational_bundle.json")
    b["intents"][0]["required_variables"] = [f"urn:nexom:variable:{uuid.uuid4()}"]
    escribir_json(d, "conversational_bundle.json", b)
    recalcular(d)


def acceptance_invalido(d: Path) -> None:
    caso = {
        "case_id": "AC-X", "query": "consulta", "user_access_level": "publico", "top_k": 3,
        "match_policy": "contains", "minimum_recall": 1.0, "expected_source_ids": [], "expected_chunk_ids": [],
        "expected_evidence_ids": [], "expected_guardrail_decision": None,
        "must_not_retrieve": [f"urn:nexom:source:{uuid.uuid4()}"],  # inexistente: prueba de denegación vacía
    }
    escribir_jsonl(d, "acceptance_cases.jsonl", [caso], clave="case_id")
    m = leer_json(d, "manifest.json")
    m["counts"]["acceptance_cases"] = 1
    escribir_json(d, "manifest.json", m)
    recalcular(d)


CASOS_DIRECTORIO: dict[str, Callable[[Path], None]] = {
    "schema_roto": schema_roto,
    "manifest_invalido": manifest_invalido,
    "checksum_roto": checksum_roto,
    "content_digest_roto": content_digest_roto,
    "source_id_incorrecto": source_id_incorrecto,
    "chunk_id_incorrecto": chunk_id_incorrecto,
    "id_duplicado": id_duplicado,
    "archivo_requerido_faltante": archivo_requerido_faltante,
    "archivo_inesperado": archivo_inesperado,
    "referencia_rota": referencia_rota,
    "cardinalidad_incorrecta": cardinalidad_incorrecta,
    "metadata_schema_invalido": metadata_schema_invalido,
    "embeddings_invalidos": embeddings_invalidos,
    "indice_sin_espacio": indice_sin_espacio,
    "access_hierarchy_invalida": access_hierarchy_invalida,
    "bundle_invalido": bundle_invalido,
    "acceptance_invalido": acceptance_invalido,
}


# ----------------------------------------------- manipulación del ZIP final

def zip_con_entrada_extra(zip_valido: Path, destino: Path) -> Path:
    shutil.copy2(zip_valido, destino)
    with zipfile.ZipFile(destino, "a") as zf:
        zf.writestr("extra/carga.bin", b"inyectado tras la publicacion")
    return destino


def zip_con_contenido_alterado(zip_valido: Path, destino: Path) -> Path:
    """Reempaqueta cambiando un texto de chunk, sin tocar checksums."""
    with zipfile.ZipFile(zip_valido) as src, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            datos = src.read(info)
            if info.filename == "chunks.jsonl":
                datos = re.sub(rb'"text":"', b'"text":"X', datos, count=1)
            dst.writestr(info, datos)
    return destino
