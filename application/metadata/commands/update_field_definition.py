"""Caso de uso: editar una definición de campo existente.

field_id y data_type son inmutables una vez creado el campo (cambiar
el tipo podría invalidar valores ya guardados sin aviso); se puede
editar display_name, obligatoriedad, filtrable, múltiple, herencia a
fragmentos, catalog_id y document_type_code. La propia FieldDefinition
(dominio) sigue exigiendo catalog_id para los tipos catálogo/selección,
así que no es posible "vaciarlo" en un campo de ese tipo por esta vía.

document_type_code sí se puede editar libremente (a diferencia de
field_id/data_type): no participa del formato del valor ya guardado
(SourceMetadataValue) -- solo decide en qué fuentes se sigue pidiendo
ese valor de aquí en adelante (ver domain.metadata.entities.
fields_applicable_to), así que reclasificar un campo de un tipo de
documento a otro nunca invalida datos ya capturados.
"""
from __future__ import annotations

from typing import Optional

from domain.metadata.entities import CATALOG_BACKED_TYPES, FieldDefinition
from domain.metadata.exceptions import (
    CatalogNotFoundError,
    CatalogRequiredForFieldTypeError,
    FieldDefinitionNotFoundError,
)
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository


class UpdateFieldDefinition:
    def __init__(self, repository: MetadataSchemaRepository, catalog_repository: CatalogRepository):
        self._repository = repository
        self._catalog_repository = catalog_repository

    def execute(
        self,
        project_id: str,
        schema_id: str,
        field_id: str,
        display_name: str,
        required: bool = False,
        filterable: bool = False,
        multiple: bool = False,
        inherited_by_chunks: bool = False,
        catalog_id: Optional[str] = None,
        document_type_code: Optional[str] = None,
    ) -> FieldDefinition:
        existing = self._repository.get_field(project_id, schema_id, field_id)
        if existing is None:
            raise FieldDefinitionNotFoundError(field_id)
        if catalog_id is not None and self._catalog_repository.get_catalog(project_id, catalog_id) is None:
            raise CatalogNotFoundError(catalog_id)
        if existing.data_type in CATALOG_BACKED_TYPES and not catalog_id:
            # Mismo chequeo explícito que AddFieldDefinition -- ver ahí
            # el porqué (evitar el pydantic.ValidationError crudo).
            raise CatalogRequiredForFieldTypeError(field_id, existing.data_type.value)

        updated = FieldDefinition(
            field_id=existing.field_id, schema_id=existing.schema_id, display_name=display_name,
            data_type=existing.data_type, required=required, filterable=filterable, multiple=multiple,
            inherited_by_chunks=inherited_by_chunks, catalog_id=catalog_id,
            document_type_code=document_type_code, created_at=existing.created_at,
        )
        self._repository.save_field(project_id, updated)
        return updated
