"""Caso de uso: eliminar un catálogo, bloqueado si algún campo del
esquema activo todavía lo referencia (RAG STUDIO.odt: un campo
catálogo/selección nunca puede quedar sin catálogo válido)."""
from __future__ import annotations

from domain.metadata.exceptions import CatalogInUseError, CatalogNotFoundError
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository


class DeleteCatalog:
    def __init__(self, catalog_repository: CatalogRepository, schema_repository: MetadataSchemaRepository):
        self._catalog_repository = catalog_repository
        self._schema_repository = schema_repository

    def execute(self, project_id: str, catalog_id: str) -> None:
        if self._catalog_repository.get_catalog(project_id, catalog_id) is None:
            raise CatalogNotFoundError(catalog_id)

        schema = self._schema_repository.get_active_schema(project_id)
        if schema is not None:
            fields = self._schema_repository.list_fields(project_id, schema.id)
            if any(f.catalog_id == catalog_id for f in fields):
                raise CatalogInUseError(catalog_id)

        self._catalog_repository.delete_catalog(project_id, catalog_id)
