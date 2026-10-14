from __future__ import annotations

from domain.metadata.entities import Catalog
from domain.metadata.ports import CatalogRepository


class ListCatalogs:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[Catalog]:
        return self._repository.list_catalogs(project_id)
