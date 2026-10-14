"""Caso de uso: agregar una entrada de catálogo, opcionalmente
jerárquica (RAG STUDIO INVESTIGACION.odt, A5: ej. Admisiones ->
Requisitos)."""
from __future__ import annotations

from typing import Optional

from domain.metadata.entities import CatalogEntry
from domain.metadata.exceptions import CatalogNotFoundError, DuplicateCatalogEntryError
from domain.metadata.ports import CatalogRepository


class AddCatalogEntry:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        catalog_id: str,
        value_code: str,
        label: str,
        parent_entry_id: Optional[str] = None,
    ) -> CatalogEntry:
        if self._repository.get_catalog(project_id, catalog_id) is None:
            raise CatalogNotFoundError(catalog_id)
        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # la unicidad de (catalog_id, value_code) ya la protege la base
        # de datos (uq_catalog_entry_code), pero sin esta verificación
        # previa quien llame recibía un IntegrityError crudo de
        # SQLAlchemy en vez de un error de dominio legible -- mismo
        # criterio que AddFieldDefinition/DuplicateFieldIdError.
        if self._repository.get_entry(project_id, catalog_id, value_code) is not None:
            raise DuplicateCatalogEntryError(catalog_id, value_code)
        if parent_entry_id is not None:
            existing_ids = {e.id for e in self._repository.list_entries(project_id, catalog_id)}
            if parent_entry_id not in existing_ids:
                raise CatalogNotFoundError(
                    f"parent_entry_id={parent_entry_id!r} no existe en el catálogo {catalog_id!r}"
                )
        entry = CatalogEntry(
            catalog_id=catalog_id, value_code=value_code, label=label, parent_entry_id=parent_entry_id
        )
        self._repository.save_entry(project_id, entry)
        return entry
