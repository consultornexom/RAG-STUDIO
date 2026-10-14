from __future__ import annotations

from domain.metadata.entities import CatalogEntry
from domain.metadata.ports import CatalogRepository


class ListCatalogEntries:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def execute(self, project_id: str, catalog_id: str) -> list[CatalogEntry]:
        return self._repository.list_entries(project_id, catalog_id)
