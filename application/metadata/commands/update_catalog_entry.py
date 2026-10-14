"""Caso de uso: editar una entrada de catálogo (etiqueta, código y/o
padre jerárquico).

Hasta la Ronda 2, value_code y catalog_id eran inmutables por diseño:
si se necesitaba otro código, había que registrar una entrada nueva.
La Ronda 3 (punto 13 de Validacion_observaciones_RAG_STUDIO.md) señaló
que esto es una variante del mismo problema ya corregido en campos de
metadatos ("Editar campo" solo permitía la etiqueta) -- aquí se
resuelve con el mismo criterio ya usado para bloquear el borrado
(DeleteCatalogEntry/CatalogEntryInUseError): el código solo se puede
cambiar mientras ninguna fuente ya tenga ese valor guardado. catalog_id
sigue siendo inmutable -- mover una entrada de catálogo no tiene el
mismo caso de uso real que corregir un código mal escrito."""
from __future__ import annotations

from typing import Optional

from domain.documents.ports import SourceRepository
from domain.metadata.entities import CatalogEntry
from domain.metadata.exceptions import (
    CatalogEntryInUseError, CatalogEntryNotFoundError, CatalogNotFoundError, DuplicateCatalogEntryError,
)
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository


class UpdateCatalogEntry:
    def __init__(
        self,
        repository: CatalogRepository,
        schema_repository: Optional[MetadataSchemaRepository] = None,
        source_repository: Optional[SourceRepository] = None,
        source_metadata_repository: Optional[SourceMetadataRepository] = None,
    ):
        self._repository = repository
        self._schema_repository = schema_repository
        self._source_repository = source_repository
        self._source_metadata_repository = source_metadata_repository

    def execute(
        self,
        project_id: str,
        catalog_id: str,
        entry_id: str,
        label: str,
        parent_entry_id: Optional[str] = None,
        value_code: Optional[str] = None,
    ) -> CatalogEntry:
        entries = self._repository.list_entries(project_id, catalog_id)
        existing = next((e for e in entries if e.id == entry_id), None)
        if existing is None:
            raise CatalogEntryNotFoundError(catalog_id, entry_id)
        if parent_entry_id is not None and not any(e.id == parent_entry_id for e in entries):
            raise CatalogNotFoundError(
                f"parent_entry_id={parent_entry_id!r} no existe en el catálogo {catalog_id!r}"
            )

        new_value_code = value_code if value_code is not None else existing.value_code
        # Ronda 88 (auditoría): cambiar el código a uno que ya usa OTRA
        # entrada del mismo catálogo terminaba en el error crudo de SQLite
        # "UNIQUE constraint failed: ... value_code" -- mismo chequeo que
        # AddCatalogEntry ya hacía al crear.
        if new_value_code != existing.value_code and any(
            e.value_code == new_value_code and e.id != existing.id for e in entries
        ):
            raise DuplicateCatalogEntryError(catalog_id, new_value_code)
        if new_value_code != existing.value_code and self._is_entry_in_use(project_id, catalog_id, existing):
            raise CatalogEntryInUseError(catalog_id, existing.value_code, action="editar el código de")

        updated = CatalogEntry(
            id=existing.id, catalog_id=existing.catalog_id, value_code=new_value_code,
            label=label, parent_entry_id=parent_entry_id,
        )
        self._repository.save_entry(project_id, updated)
        return updated

    def _is_entry_in_use(self, project_id: str, catalog_id: str, entry: CatalogEntry) -> bool:
        """Mismo chequeo que DeleteCatalogEntry: ¿alguna fuente del
        proyecto ya tiene el código actual de esta entrada guardado como
        valor de un campo vinculado a este catálogo? Si no se
        configuraron los repositorios adicionales (uso sin verificación,
        pensado para compatibilidad hacia atrás con quien solo pase
        `repository`), se asume que no está en uso -- igual que antes de
        esta mejora, cuando el código simplemente no se podía cambiar."""
        if self._schema_repository is None or self._source_repository is None \
                or self._source_metadata_repository is None:
            return False

        schema = self._schema_repository.get_active_schema(project_id)
        if schema is None:
            return False
        field_ids_using_catalog = {
            f.field_id for f in self._schema_repository.list_fields(project_id, schema.id)
            if f.catalog_id == catalog_id
        }
        if not field_ids_using_catalog:
            return False
        for source in self._source_repository.list_for_project(project_id):
            for value in self._source_metadata_repository.list_values_for_source(project_id, source.id):
                if value.field_id in field_ids_using_catalog and entry.value_code in value.value.split("|"):
                    return True
        return False
