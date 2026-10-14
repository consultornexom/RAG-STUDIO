from __future__ import annotations

from domain.metadata.entities import FieldDefinition, MetadataSchema
from domain.metadata.exceptions import MetadataDomainError
from domain.metadata.ports import MetadataSchemaRepository


class GetMetadataSchema:
    def __init__(self, repository: MetadataSchemaRepository):
        self._repository = repository

    def execute(self, project_id: str) -> tuple[MetadataSchema, list[FieldDefinition]]:
        schema = self._repository.get_active_schema(project_id)
        if schema is None:
            raise MetadataDomainError(f"No hay esquema de metadatos activo para {project_id!r}")
        return schema, self._repository.list_fields(project_id, schema.id)
