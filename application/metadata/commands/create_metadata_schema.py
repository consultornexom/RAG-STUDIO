"""Caso de uso: crear el esquema de metadatos activo de un proyecto."""
from __future__ import annotations

from domain.metadata.entities import MetadataSchema
from domain.metadata.exceptions import SchemaAlreadyExistsError
from domain.metadata.ports import MetadataSchemaRepository


class CreateMetadataSchema:
    def __init__(self, repository: MetadataSchemaRepository):
        self._repository = repository

    def execute(self, project_id: str) -> MetadataSchema:
        if self._repository.get_active_schema(project_id) is not None:
            raise SchemaAlreadyExistsError(project_id)
        schema = MetadataSchema(project_id=project_id)
        self._repository.save_schema(schema)
        return schema
