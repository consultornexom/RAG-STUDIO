"""Compuerta de conformidad del NEXOM Knowledge Package v1.0.0 (RAG-INC-01c).

1. **Integridad del contrato vendorizado.** Antes de validar nada se
   comprueba que los 16 artefactos normativos de
   `contracts/nexom_knowledge_package/v1_0_0/` tienen exactamente el SHA-256
   firmado (Declaración de aceptación §4.1). Si alguno difiere, toda
   validación devuelve FAIL (fail-closed): nunca se valida contra un contrato
   alterado.
2. **Validador firmado.** Se ejecuta `validate_knowledge_package.py` v1.0.0
   en el mismo proceso (`run_validation`), sin modificarlo: schemas con
   FormatChecker, integridad referencial, continuidad de linaje y recomputo de
   `source.id`/`chunk.id`, igualdad de conjuntos de archivos, conteos,
   perfil, capacidades/omisiones, semántica de casos de aceptación,
   checksums y, si se entrega el sidecar, `content_digest`.
3. **Comprobaciones adicionales de RAG Studio (más estrictas, nunca más
   laxas).** Unicidad de identificadores dentro de cada colección del
   paquete. El validador firmado indexa los registros por `id` en
   diccionarios, de modo que un registro con `id` repetido no se detecta
   (RAG-INC-01c lo demostró). La compuerta lo rechaza; no se modifica el
   contrato.

Resultado: PASS solo si no hay ningún error de ninguna de las tres partes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from argparse import Namespace
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from contracts.nexom_knowledge_package import V1_0_0_DIR, VENDORED_INDEX, load_validator
from domain.knowledge_package.conformance import (
    ConformanceCategory,
    ConformanceIssue,
    ConformanceReport,
    ConformanceStatus,
)
from domain.knowledge_package.entities import CONTRACT_SCHEMA_VERSION
from domain.knowledge_package.ports import KnowledgePackageConformanceValidator

logger = logging.getLogger(__name__)

ORIGEN_FIRMADO = "validador_firmado"
ORIGEN_RAG_STUDIO = "rag_studio"

_PREFIJOS = (
    ("[autochequeo]", ConformanceCategory.CONTRATO),
    ("[seguridad-zip]", ConformanceCategory.ZIP),
    ("[schema]", ConformanceCategory.SCHEMA),
    ("[referencial]", ConformanceCategory.REFERENCIA),
    ("[ids]", ConformanceCategory.IDS),
    ("[archivos]", ConformanceCategory.ESTRUCTURA),
    ("[conteos]", ConformanceCategory.CARDINALIDAD),
    ("[perfil]", ConformanceCategory.PERFIL),
    ("[omisiones]", ConformanceCategory.CAPACIDADES),
    ("[capacidades]", ConformanceCategory.CAPACIDADES),
    ("[aceptacion]", ConformanceCategory.ACEPTACION),
    ("[checksums]", ConformanceCategory.CHECKSUM),
    ("[sidecar]", ConformanceCategory.CONTENT_DIGEST),
    ("[firma]", ConformanceCategory.CONTENT_DIGEST),
)

_COLECCIONES_JSONL = {
    "sources.jsonl": "id", "chunks.jsonl": "id", "evidence.jsonl": "id", "media.jsonl": "id",
    "source_metadata.jsonl": "id", "acceptance_cases.jsonl": "case_id",
}


def _categoria(mensaje: str) -> ConformanceCategory:
    for prefijo, categoria in _PREFIJOS:
        if mensaje.startswith(prefijo):
            return categoria
    return ConformanceCategory.OTRO


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def verificar_contrato_vendorizado() -> list[str]:
    """Diferencias entre los artefactos NORMATIVOS vendorizados y su hash
    firmado. Lista vacía = contrato íntegro."""
    try:
        indice = json.loads(VENDORED_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"índice del contrato vendorizado ilegible: {exc}"]
    normativos = [e for e in indice.get("archivos", []) if "§4.1" in e.get("fuente_del_esperado", "")]
    if len(normativos) != 16:
        return [f"el índice declara {len(normativos)} artefactos normativos (esperados 16)"]
    diferencias = []
    for entrada in normativos:
        ruta = V1_0_0_DIR / entrada["ruta"]
        if not ruta.is_file():
            diferencias.append(f"falta {entrada['ruta']}")
        elif _sha256(ruta) != entrada["sha256_esperado"]:
            diferencias.append(f"{entrada['ruta']} no coincide con el SHA-256 firmado")
    return diferencias


class _LectorPaquete:
    """Lee archivos del paquete, sea directorio o ZIP, sin extraer."""

    def __init__(self, ruta: Path):
        self._ruta = ruta
        self._zip = zipfile.ZipFile(ruta) if ruta.is_file() else None

    def cerrar(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def texto(self, nombre: str) -> Optional[str]:
        try:
            if self._zip is not None:
                return self._zip.read(nombre).decode("utf-8")
            return (self._ruta / nombre).read_text(encoding="utf-8")
        except (KeyError, OSError, UnicodeDecodeError):
            return None


def _duplicados(valores: list[Any]) -> list[Any]:
    return sorted(v for v, n in Counter(valores).items() if n > 1)


def comprobar_unicidad(ruta: Path) -> list[str]:
    """Identificadores repetidos dentro de cada colección del paquete."""
    lector = _LectorPaquete(ruta)
    errores: list[str] = []
    try:
        for archivo, clave in _COLECCIONES_JSONL.items():
            texto = lector.texto(archivo)
            if texto is None:
                continue  # su ausencia la reporta el validador firmado
            try:
                registros = [json.loads(linea) for linea in texto.splitlines() if linea.strip()]
            except json.JSONDecodeError:
                continue  # JSON inválido: lo reporta el validador firmado
            for dup in _duplicados([r.get(clave) for r in registros if isinstance(r, dict)]):
                errores.append(f"{archivo}: {clave} repetido {dup}")

        def lista(archivo: str, *camino: str) -> list[Any]:
            texto = lector.texto(archivo)
            if texto is None:
                return []
            try:
                obj: Any = json.loads(texto)
            except json.JSONDecodeError:
                return []
            for paso in camino:
                obj = obj.get(paso, []) if isinstance(obj, dict) else []
            return obj if isinstance(obj, list) else []

        colecciones = {
            "conversational_bundle.json/intents": lista("conversational_bundle.json", "intents"),
            "conversational_bundle.json/guardrail_rules": lista("conversational_bundle.json", "guardrail_rules"),
            "conversational_bundle.json/conversational_variables": lista("conversational_bundle.json", "conversational_variables"),
            "conversational_bundle.json/channeling_schemes": lista("conversational_bundle.json", "channeling_schemes"),
            "metadata_schema.json/fields": lista("metadata_schema.json", "fields"),
            "metadata_schema.json/catalogs": lista("metadata_schema.json", "catalogs"),
            "embedding_spaces.json": lista("embedding_spaces.json"),
            "indexes.json": lista("indexes.json"),
        }
        for nombre, registros in colecciones.items():
            for dup in _duplicados([r.get("id") for r in registros if isinstance(r, dict)]):
                errores.append(f"{nombre}: id repetido {dup}")
        for catalogo in colecciones["metadata_schema.json/catalogs"]:
            if isinstance(catalogo, dict):
                codigos = [e.get("value_code") for e in catalogo.get("entries", []) if isinstance(e, dict)]
                for dup in _duplicados(codigos):
                    errores.append(f"metadata_schema.json/catalogs[{catalogo.get('name')}]: value_code repetido {dup}")
    finally:
        lector.cerrar()
    return errores


class ContractV1ConformanceValidator(KnowledgePackageConformanceValidator):
    """Compuerta de conformidad contra el contrato NKP v1.0.0 vendorizado."""

    def __init__(self) -> None:
        self._diferencias_contrato = verificar_contrato_vendorizado()
        if self._diferencias_contrato:
            logger.error("Contrato NKP vendorizado alterado: %s", self._diferencias_contrato)

    def validate(self, package_path: str, content_digest_file: Optional[str] = None) -> ConformanceReport:
        issues: list[ConformanceIssue] = []
        if self._diferencias_contrato:
            issues = [ConformanceIssue(ConformanceCategory.CONTRATO, f"contrato vendorizado alterado: {d}", ORIGEN_RAG_STUDIO)
                      for d in self._diferencias_contrato]
            return ConformanceReport(ConformanceStatus.FAIL, CONTRACT_SCHEMA_VERSION, 0, tuple(issues))

        ruta = Path(package_path)
        ok = 0
        try:
            validador = load_validator()
            args = Namespace(
                package=ruta, content_digest_file=Path(content_digest_file) if content_digest_file else None,
                signature_file=None, public_key=None, trusted_key_id=None, zip_sha256_file=None,
            )
            reporte = validador.run_validation(args)
            ok = len(reporte.ok)
            issues += [ConformanceIssue(_categoria(m), m, ORIGEN_FIRMADO) for m in reporte.errors]
        except Exception as exc:  # noqa: BLE001 - ValidationAborted u otro: siempre FAIL, nunca PASS
            issues.append(ConformanceIssue(
                ConformanceCategory.CONTRATO if "dependencia" in str(exc) else ConformanceCategory.OTRO,
                f"el validador firmado no pudo completar la validación: {type(exc).__name__}: {exc}", ORIGEN_FIRMADO,
            ))

        try:
            issues += [ConformanceIssue(ConformanceCategory.UNICIDAD, m, ORIGEN_RAG_STUDIO) for m in comprobar_unicidad(ruta)]
        except (OSError, zipfile.BadZipFile) as exc:
            issues.append(ConformanceIssue(ConformanceCategory.ZIP, f"no se pudo leer el paquete: {exc}", ORIGEN_RAG_STUDIO))

        estado = ConformanceStatus.PASS if not issues else ConformanceStatus.FAIL
        return ConformanceReport(estado, CONTRACT_SCHEMA_VERSION, ok, tuple(issues))
