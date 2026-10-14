"""Caso de uso: asignar el valor de un campo a una fuente concreta.

No relaja validaciones silenciosamente (Documento Maestro, sección 4):
valida tipo, obligatoriedad, multiplicidad y pertenencia a catálogo
antes de guardar.
"""
from __future__ import annotations

from typing import Union

from domain.metadata.entities import CATALOG_BACKED_TYPES, SourceMetadataValue
from domain.metadata.exceptions import FieldDefinitionNotFoundError, InvalidMetadataValueError
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository


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
        field = self._schema_repository.get_field(project_id, schema_id, field_id)
        if field is None:
            raise FieldDefinitionNotFoundError(field_id)

        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not field.multiple and len(values) > 1:
            raise InvalidMetadataValueError(f"El campo {field_id!r} no admite múltiples valores")
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
    ) -> SourceMetadataValue:
        values = self.validate(project_id, schema_id, field_id, raw_value)
        serialized = "|".join(str(v) for v in values)
        value = SourceMetadataValue(source_id=source_id, field_id=field_id, value=serialized)
        self._source_metadata_repository.save_value(project_id, value)
        return value
