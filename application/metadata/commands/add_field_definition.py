"""Caso de uso: agregar una definición de campo al esquema.

La validación de que los tipos catálogo/selección requieran
catalog_id vive en el dominio (FieldDefinition); aquí solo se valida
lo que depende de otros agregados: unicidad de field_id y existencia
del catálogo referenciado.
"""
from __future__ import annotations

from typing import Optional

from domain.metadata.entities import CATALOG_BACKED_TYPES, FieldDataType, FieldDefinition
from domain.metadata.exceptions import CatalogNotFoundError, CatalogRequiredForFieldTypeError, DuplicateFieldIdError
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository


class AddFieldDefinition:
    def __init__(self, repository: MetadataSchemaRepository, catalog_repository: CatalogRepository):
        self._repository = repository
        self._catalog_repository = catalog_repository

    def execute(
        self,
        project_id: str,
        schema_id: str,
        field_id: str,
        display_name: str,
        data_type: FieldDataType,
        required: bool = False,
        filterable: bool = False,
        multiple: bool = False,
        inherited_by_chunks: bool = False,
        catalog_id: Optional[str] = None,
        document_type_code: Optional[str] = None,
    ) -> FieldDefinition:
        if self._repository.get_field(project_id, schema_id, field_id) is not None:
            raise DuplicateFieldIdError(field_id)
        if catalog_id is not None and self._catalog_repository.get_catalog(project_id, catalog_id) is None:
            raise CatalogNotFoundError(catalog_id)
        if data_type in CATALOG_BACKED_TYPES and not catalog_id:
            # Chequeo explícito antes de construir FieldDefinition: sin
            # esto, el mismo caso lo detecta el model_validator del
            # dominio, pero como pydantic.ValidationError crudo -- un
            # mensaje técnico que se le mostraba tal cual al usuario en
            # la UI (hallazgo real de validación visual). Con este
            # chequeo primero, nunca se llega a construir el modelo en
            # este caso, así que siempre se ve el mensaje de dominio.
            raise CatalogRequiredForFieldTypeError(field_id, data_type.value if hasattr(data_type, "value") else str(data_type))

        field = FieldDefinition(
            field_id=field_id, schema_id=schema_id, display_name=display_name, data_type=data_type,
            required=required, filterable=filterable, multiple=multiple,
            inherited_by_chunks=inherited_by_chunks, catalog_id=catalog_id,
            document_type_code=document_type_code,
        )
        self._repository.save_field(project_id, field)
        return field
