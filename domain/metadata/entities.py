"""Metamodelo dinámico: MetadataSchema, FieldDefinition, Catalog,
CatalogEntry y SourceMetadataValue (ADR-001, sección 5 — contexto
"Metadatos"; RAG STUDIO.odt, sección 7).

Regla de diseño no negociable (RAG STUDIO.odt, sección 21): nunca crear
campos de negocio en el código (nada de `document.campus`); todo campo
vive como una FieldDefinition, y su valor por fuente como
SourceMetadataValue.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FieldDataType(str, Enum):
    TEXTO = "texto"
    TEXTO_LARGO = "texto_largo"
    NUMERO = "numero"
    DECIMAL = "decimal"
    FECHA = "fecha"
    FECHA_HORA = "fecha_hora"
    BOOLEANO = "booleano"
    SELECCION_UNICA = "seleccion_unica"
    SELECCION_MULTIPLE = "seleccion_multiple"
    CATALOGO_JERARQUICO = "catalogo_jerarquico"
    URL = "url"
    IDENTIFICADOR = "identificador"
    NIVEL_SEGURIDAD = "nivel_seguridad"
    ESTADO = "estado"
    RELACION = "relacion"


CATALOG_BACKED_TYPES = frozenset({
    FieldDataType.SELECCION_UNICA, FieldDataType.SELECCION_MULTIPLE, FieldDataType.CATALOGO_JERARQUICO,
})
"""Tipos que RAG STUDIO INVESTIGACION.odt exige resolver por catálogo,
nunca por texto libre (ej. programa, plantel, modalidad)."""

FREE_TEXT_TYPES = frozenset({FieldDataType.TEXTO, FieldDataType.TEXTO_LARGO})
"""Tipos considerados "texto libre no controlado" para el reporte de
cobertura (criterio de aceptación de A1: máximo 5% de los valores)."""


def fields_applicable_to(fields: "list[FieldDefinition]", document_type_code: str) -> "list[FieldDefinition]":
    """Filtra los campos del esquema que aplican a una fuente con este
    document_type_code: los genéricos (document_type_code=None) más
    los que coinciden exactamente. Punto único de esta regla -- la
    usan tanto "Valores por fuente" (ui/metadata/panel.py) como el
    reporte de Cobertura (application/metadata/queries/get_coverage_report.py),
    para no duplicar el criterio en dos lugares y arriesgar que se
    desincronicen."""
    return [f for f in fields if f.document_type_code is None or f.document_type_code == document_type_code]


class MetadataSchema(BaseModel):
    """Un esquema de metadatos versionado, por proyecto."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class FieldDefinition(BaseModel):
    """Definición de un campo dentro de un esquema. field_id es estable
    y no debe depender del nombre visible (display_name puede cambiar)."""

    field_id: str
    schema_id: str
    display_name: str
    data_type: FieldDataType
    required: bool = False
    filterable: bool = False
    multiple: bool = False
    inherited_by_chunks: bool = False
    catalog_id: Optional[str] = None
    document_type_code: Optional[str] = None
    """Acota este campo a las fuentes con ese document_type_code (ver
    domain.documents.entities.Source.document_type_code) -- observación
    real de usuario, ver docs proyecto/Validacion_observaciones_RAG_STUDIO.md,
    punto 10. None (el valor por defecto, y el de todos los esquemas
    creados antes de este cambio) significa "campo genérico": aplica a
    toda fuente del proyecto sin importar su tipo, igual que el
    comportamiento de siempre. Ver fields_applicable_to."""
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("field_id")
    @classmethod
    def _field_id_formato(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError(
                f"field_id inválido ({v!r}): usa solo letras ASCII, números y guion "
                "bajo, sin espacios ni acentos (ej. 'campus_id')."
            )
        return v

    @model_validator(mode="after")
    def _catalog_required_for_catalog_backed_types(self) -> "FieldDefinition":
        if self.data_type in CATALOG_BACKED_TYPES and not self.catalog_id:
            raise ValueError(
                f"El campo {self.field_id!r} es de tipo {self.data_type.value!r} y debe "
                "referenciar un catalog_id; RAG STUDIO no permite texto libre para "
                "programa/plantel/modalidad ni campos equivalentes (RAG STUDIO.odt, "
                "reglas de diseño A1)."
            )
        return self


class Catalog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    created_at: datetime = Field(default_factory=_utcnow)


class CatalogEntry(BaseModel):
    """Entrada de catálogo, opcionalmente jerárquica (ej. Admisiones ->
    Requisitos -> Fechas, RAG STUDIO INVESTIGACION.odt, A5)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    catalog_id: str
    value_code: str
    label: str
    parent_entry_id: Optional[str] = None


MULTI_VALUE_SEPARATOR = "|"
"""Separador con el que se guardan los campos de varios valores
(multiple=True) en SourceMetadataValue.value. Ya lo usaban el filtro de
recuperación, el exportador NKP y las comprobaciones de catálogo en uso;
estas dos funciones son el punto único para el código nuevo."""


def split_stored_values(value: Optional[str]) -> list[str]:
    """Lista de valores de un SourceMetadataValue.value: separa por '|',
    quita espacios y vacíos, conserva el orden y elimina repetidos."""
    if not value:
        return []
    return list(dict.fromkeys(v.strip() for v in value.split(MULTI_VALUE_SEPARATOR) if v.strip()))


def join_values(values: "list[str]") -> str:
    return MULTI_VALUE_SEPARATOR.join(values)


class SourceMetadataValue(BaseModel):
    """Valor de un campo para una fuente concreta. Los valores multi-
    valor (multiple=True en su FieldDefinition) se serializan como
    lista de códigos separados por '|' (MULTI_VALUE_SEPARATOR)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    field_id: str
    value: str
    created_at: datetime = Field(default_factory=_utcnow)


class MetadataValueChange(BaseModel):
    """Entrada de auditoría (ítem 5 de la evaluación de madurez
    post-8-etapas): un registro append-only de cada vez que
    `save_value` cambió de verdad el valor vigente de un campo para
    una fuente -- `SourceMetadataValue` sigue siendo upsert (solo el
    valor vigente), esto es lo que faltaba para poder responder "¿cuál
    era el valor antes, y cuándo cambió?". `previous_value=None`
    identifica la primera asignación (creación, no edición) de ese
    campo para esa fuente."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    field_id: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    """None identifica que el campo quedó sin asignar tras este cambio
    -- Ronda 6, punto 23 de Validacion_observaciones_RAG_STUDIO.md
    (hallazgo real de usuario, video 3): antes no había forma de
    desasociar un valor ya guardado, así que new_value siempre era un
    str; ahora DeleteSourceMetadataValue puede dejarlo en None, mismo
    significado que previous_value=None pero en el otro sentido (aquí
    "sin asignar" es el estado de llegada, no el de partida)."""
    changed_at: datetime = Field(default_factory=_utcnow)
