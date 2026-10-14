"""Identidad y trazabilidad de los LOTES de RAG CONTENT importados en un
proyecto (Ronda 92, 2026-10-06, SOLICITUD NEXOM "Hallazgo de
portabilidad, identidad y preparación multi-lote").

Antes, "Importar carpeta de RAG CONTENT…" registraba fuentes sueltas: no
quedaba ningún rastro de QUÉ lote las trajo, si un lote ya se había
importado, ni si una carpeta era una versión nueva de un lote anterior.
Un proyecto puede recibir lotes distintos en momentos distintos y desde
equipos distintos; los consumidores posteriores (Testing Agent, Runtime)
necesitan esa procedencia.

Reglas (documento 08 de la solicitud):
- La huella del lote (`batch_fingerprint`) depende SOLO del contenido
  lógico declarado: pares (nombre de archivo, hash_contenido) ordenados.
  No participan rutas absolutas, carpeta de importación, equipo,
  usuario, fecha ni el orden de las filas. El mismo lote copiado a otro
  equipo da la misma huella; cambiar el contenido de un documento da
  otra.
- Para V2 se usa `ruta_archivo` (relativa, ya validada); para V1 solo
  el nombre del archivo (la ruta absoluta del equipo productor no es
  identidad). Separadores normalizados a "/" y Unicode a NFC.
- La relación con lotes anteriores se CLASIFICA, nunca se aplica en
  silencio: importar una versión nueva no retira ni sustituye fuentes
  del lote anterior (eso sigue siendo decisión explícita del usuario,
  con "Sustituye a"). La consolidación final corresponde a los
  consumidores posteriores.
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .manifest import es_manifiesto_v2, extraer_nombre_base_multiplataforma


class BatchRelation(str, Enum):
    NUEVO = "lote_nuevo"
    """Ningún documento en común con lotes ya importados."""
    REIMPORTACION = "reimportacion_identica"
    """Misma huella que un lote ya importado: no se duplica nada."""
    NUEVA_VERSION = "nueva_version"
    """Comparte documentos (por nombre) con un lote anterior, pero su
    contenido difiere: versión nueva/corrección de ese lote."""
    AMPLIACION = "comparte_documentos"
    """Comparte documentos idénticos con un lote anterior y agrega otros
    (o es un subconjunto): ni duplicado exacto ni versión nueva."""


def nombre_logico(ruta_archivo: str, manifest_schema_version: Optional[str]) -> str:
    """Nombre del documento dentro del lote, independiente del equipo."""
    ruta = (ruta_archivo or "").strip()
    if not es_manifiesto_v2(manifest_schema_version):
        ruta = extraer_nombre_base_multiplataforma(ruta)
    return unicodedata.normalize("NFC", ruta.replace("\\", "/"))


def batch_fingerprint(entries: list[tuple[str, str]]) -> str:
    """`entries` = [(nombre_logico, hash_contenido)]. Orden irrelevante."""
    canonico = "\n".join(
        f"{nombre}\t{(hash_ or '').strip().lower()}" for nombre, hash_ in sorted(set(entries))
    )
    return "sha256:" + hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ImportBatchRow:
    titulo: str
    nombre: str
    hash_contenido: str
    resultado: str
    source_id: Optional[str] = None


@dataclass(frozen=True)
class ImportBatchRecord:
    fingerprint: str
    label: str
    manifest_schema_version: str
    imported_at: str
    relation: str
    related_label: Optional[str] = None
    rows: tuple[ImportBatchRow, ...] = field(default_factory=tuple)
    complete: bool = True
    """False si alguna fila se omitió por algo distinto de "ya estaba
    registrada" (archivo faltante, hash distinto...): ese intento no
    cuenta como lote ya importado para clasificar reimportaciones."""

    def documentos(self) -> dict[str, str]:
        return {row.nombre: row.hash_contenido for row in self.rows}


def classify_batch(
    fingerprint: str, documentos: dict[str, str], previous: list[ImportBatchRecord],
) -> tuple[BatchRelation, Optional[ImportBatchRecord]]:
    """Relación del lote que se importa con los ya importados (el más
    reciente que aplique)."""
    for anterior in reversed(previous):
        if anterior.fingerprint == fingerprint and anterior.complete:
            return BatchRelation.REIMPORTACION, anterior
    for anterior in reversed(previous):
        if anterior.fingerprint == fingerprint:
            continue  # intento incompleto del MISMO lote: no es otra versión
        previos = anterior.documentos()
        comunes = set(previos) & set(documentos)
        if not comunes:
            continue
        if any(previos[n] != documentos[n] for n in comunes):
            return BatchRelation.NUEVA_VERSION, anterior
        return BatchRelation.AMPLIACION, anterior
    return BatchRelation.NUEVO, None
