"""Caso de uso: eliminar una entrada de catálogo, bloqueado si alguna
fuente del proyecto todavía tiene ese código guardado como valor de
metadatos (evita dejar valores huérfanos que ya no resuelven en el
catálogo, en línea con la regla de A1 de no permitir texto libre no
controlado)."""
from __future__ import annotations

from domain.documents.ports import SourceRepository
from domain.metadata.exceptions import CatalogEntryInUseError, CatalogEntryNotFoundError
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository


class DeleteCatalogEntry:
    def __init__(
        self,
        catalog_repository: CatalogRepository,
        schema_repository: MetadataSchemaRepository,
        source_repository: SourceRepository,
        source_metadata_repository: SourceMetadataRepository,
    ):
        self._catalog_repository = catalog_repository
        self._schema_repository = schema_repository
        self._source_repository = source_repository
        self._source_metadata_repository = source_metadata_repository

    def execute(self, project_id: str, catalog_id: str, entry_id: str) -> None:
        entries = self._catalog_repository.list_entries(project_id, catalog_id)
        entry = next((e for e in entries if e.id == entry_id), None)
        if entry is None:
            raise CatalogEntryNotFoundError(catalog_id, entry_id)

        schema = self._schema_repository.get_active_schema(project_id)
        if schema is not None:
            field_ids_using_catalog = {
                f.field_id for f in self._schema_repository.list_fields(project_id, schema.id)
                if f.catalog_id == catalog_id
            }
            if field_ids_using_catalog:
                for source in self._source_repository.list_for_project(project_id):
                    for value in self._source_metadata_repository.list_values_for_source(project_id, source.id):
                        if value.field_id in field_ids_using_catalog and entry.value_code in value.value.split("|"):
                            raise CatalogEntryInUseError(catalog_id, entry.value_code)

        self._catalog_repository.delete_entry(project_id, catalog_id, entry_id)
