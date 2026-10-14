"""Caso de uso: renombrar un catálogo existente. El id es estable;
solo cambia el nombre visible."""
from __future__ import annotations

from domain.metadata.entities import Catalog
from domain.metadata.exceptions import CatalogNotFoundError
from domain.metadata.ports import CatalogRepository


class UpdateCatalog:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def execute(self, project_id: str, catalog_id: str, name: str) -> Catalog:
        existing = self._repository.get_catalog(project_id, catalog_id)
        if existing is None:
            raise CatalogNotFoundError(catalog_id)
        updated = Catalog(
            id=existing.id, project_id=existing.project_id, name=name, created_at=existing.created_at,
        )
        self._repository.save_catalog(updated)
        return updated
