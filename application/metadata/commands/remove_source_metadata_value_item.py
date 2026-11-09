"""Caso de uso: quitar UN valor de un campo de varios valores, conservando
los demás (Ronda 97, hallazgo real de NEXOM, AGENTE UDL).

Antes solo existía DeleteSourceMetadataValue, que quita el campo completo
de la fuente: para corregir `campus = [hilario_medina, torres_landa]` a
solo `hilario_medina` había que borrar todo y volver a capturar.

- Si el valor no está asignado a la fuente, error de dominio claro
  (SourceMetadataValueNotFoundError), en vez de un "borrado" silencioso.
- Si era el último valor, el campo queda sin asignar (mismo efecto y
  mismo rastro de auditoría que DeleteSourceMetadataValue).
- El historial (metadata_value_change) registra el cambio, igual que
  cualquier otro guardado.
"""
from __future__ import annotations

from domain.metadata.entities import SourceMetadataValue, join_values, split_stored_values
from domain.metadata.exceptions import (
    FieldDefinitionNotFoundError,
    InvalidMetadataValueError,
    SourceMetadataValueNotFoundError,
)
from domain.metadata.ports import MetadataSchemaRepository, SourceMetadataRepository


class RemoveSourceMetadataValueItem:
    def __init__(self, schema_repository: MetadataSchemaRepository, source_metadata_repository: SourceMetadataRepository):
        self._schema_repository = schema_repository
        self._source_metadata_repository = source_metadata_repository

    def execute(self, project_id: str, schema_id: str, source_id: str, field_id: str, item: str) -> list[str]:
        """Devuelve los valores que quedan asignados (lista vacía si el
        campo quedó sin asignar)."""
        field = self._schema_repository.get_field(project_id, schema_id, field_id)
        if field is None:
            raise FieldDefinitionNotFoundError(field_id)
        if not field.multiple:
            raise InvalidMetadataValueError(
                f"El campo {field_id!r} no es de varios valores: use \"Quitar valor\" del campo completo."
            )
        existente = self._source_metadata_repository.get_value(project_id, source_id, field_id)
        actuales = split_stored_values(existente.value if existente else None)
        if existente is None or item not in actuales:
            raise SourceMetadataValueNotFoundError(source_id, f"{field_id}={item}")
        restantes = [v for v in actuales if v != item]
        if restantes:
            self._source_metadata_repository.save_value(
                project_id, SourceMetadataValue(source_id=source_id, field_id=field_id, value=join_values(restantes)),
            )
        else:
            self._source_metadata_repository.delete_value(project_id, source_id, field_id)
        return restantes
