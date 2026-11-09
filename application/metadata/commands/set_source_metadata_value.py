"""Caso de uso: asignar el valor de un campo a una fuente concreta.

No relaja validaciones silenciosamente (Documento Maestro, sección 4):
valida tipo, obligatoriedad, multiplicidad y pertenencia a catálogo
antes de guardar.

Ronda 97 (hallazgo real de NEXOM, AGENTE UDL, prioridad alta): un campo
de varios valores con catálogo (p. ej. `campus` = hilario_medina y
torres_landa) solo podía guardar UN valor desde la interfaz -- cada
"Guardar valor" sustituía al anterior. El guardado ya aceptaba listas;
lo que faltaba:
- `mode="agregar"`: une los valores nuevos a los que la fuente ya tiene
  (sin repetir), en vez de reemplazarlos. Solo para campos de varios
  valores. `mode="reemplazar"` (por defecto) es el comportamiento de
  siempre: el valor guardado pasa a ser exactamente el indicado.
- en campos de varios valores, cada valor se valida por separado: no
  puede estar vacío ni contener el separador '|' (rompería la lista
  guardada), y los repetidos se eliminan conservando el orden.
"""
from __future__ import annotations

from enum import Enum
from typing import Union

from domain.metadata.entities import (
    CATALOG_BACKED_TYPES,
    MULTI_VALUE_SEPARATOR,
    SourceMetadataValue,
    join_values,
    split_stored_values,
)
from domain.metadata.exceptions import FieldDefinitionNotFoundError, InvalidMetadataValueError
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository


class ValueAssignmentMode(str, Enum):
    REEMPLAZAR = "reemplazar"
    AGREGAR = "agregar"


def parse_mode(mode: object) -> ValueAssignmentMode:
    try:
        return ValueAssignmentMode(getattr(mode, "value", mode))
    except ValueError:
        raise InvalidMetadataValueError(
            f"Modo de asignación desconocido {mode!r}: use 'reemplazar' o 'agregar'."
        ) from None


class SetSourceMetadataValue:
    def __init__(
        self,
        schema_repository: MetadataSchemaRepository,
        catalog_repository: CatalogRepository,
        source_metadata_repository: SourceMetadataRepository,
    ):
        self._schema_repository = schema_repository
        self._catalog_repository = catalog_repository
        self._source_metadata_repository = source_metadata_repository

    def validate(
        self,
        project_id: str,
        schema_id: str,
        field_id: str,
        raw_value: Union[str, list[str]],
        mode: object = ValueAssignmentMode.REEMPLAZAR,
    ) -> list[str]:
        """Valida field_id/raw_value contra la FieldDefinition (tipo,
        obligatoriedad, multiplicidad, pertenencia a catálogo) SIN
        depender de ninguna fuente concreta y sin guardar nada --
        `execute` la reutiliza, y BulkSetSourceMetadataValue la llama
        directamente para validar una sola vez, antes de saber si
        alguna de las fuentes del lote todavía existe (Ronda 6:
        auditoría posterior a la Ronda 5 encontró que, si todas las
        fuentes del lote habían dejado de existir, un field_id/valor
        inválido pasaba sin detectarse porque la validación solo
        ocurría dentro de execute(), y execute() solo se invocaba por
        fuente ya confirmada como existente)."""
        modo = parse_mode(mode)
        field = self._schema_repository.get_field(project_id, schema_id, field_id)
        if field is None:
            raise FieldDefinitionNotFoundError(field_id)

        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not field.multiple and len(values) > 1:
            raise InvalidMetadataValueError(f"El campo {field_id!r} no admite múltiples valores")
        if modo is ValueAssignmentMode.AGREGAR and not field.multiple:
            raise InvalidMetadataValueError(
                f"El campo {field_id!r} no admite varios valores: no se puede agregar, solo reemplazar."
            )
        if field.multiple:
            # Ronda 97: cada valor de un campo multivalor se valida por separado.
            for v in values:
                if not isinstance(v, str) or not v.strip():
                    raise InvalidMetadataValueError(f"El campo {field_id!r} recibió un valor vacío en la lista.")
                if MULTI_VALUE_SEPARATOR in v:
                    raise InvalidMetadataValueError(
                        f"El valor {v!r} del campo {field_id!r} contiene '{MULTI_VALUE_SEPARATOR}', que se usa "
                        "para separar varios valores; indíquelos como elementos distintos."
                    )
            values = list(dict.fromkeys(values))
        if modo is ValueAssignmentMode.AGREGAR and not values:
            raise InvalidMetadataValueError(f"No hay ningún valor que agregar al campo {field_id!r}.")
        if field.required and not values:
            raise InvalidMetadataValueError(f"El campo {field_id!r} es obligatorio")

        if field.data_type in CATALOG_BACKED_TYPES:
            # AddFieldDefinition ya exige catalog_id para estos tipos de
            # dato al crear el campo (ver add_field_definition.py); esta
            # comprobación es una red de seguridad interna, no debería
            # dispararse nunca en la práctica.
            if not field.catalog_id:
                raise InvalidMetadataValueError(
                    f"El campo {field_id!r} no tiene catálogo asignado (inconsistencia interna)"
                )
            for v in values:
                if self._catalog_repository.get_entry(project_id, field.catalog_id, v) is None:
                    raise InvalidMetadataValueError(
                        f"{v!r} no existe en el catálogo {field.catalog_id!r} (campo {field_id!r})"
                    )
        return values

    def execute(
        self,
        project_id: str,
        schema_id: str,
        source_id: str,
        field_id: str,
        raw_value: Union[str, list[str]],
        mode: object = ValueAssignmentMode.REEMPLAZAR,
    ) -> SourceMetadataValue:
        modo = parse_mode(mode)
        values = self.validate(project_id, schema_id, field_id, raw_value, modo)
        if modo is ValueAssignmentMode.AGREGAR:
            existente = self._source_metadata_repository.get_value(project_id, source_id, field_id)
            previos = split_stored_values(existente.value if existente else None)
            values = list(dict.fromkeys(previos + values))
        serialized = join_values([str(v) for v in values])
        value = SourceMetadataValue(source_id=source_id, field_id=field_id, value=serialized)
        self._source_metadata_repository.save_value(project_id, value)
        return value
