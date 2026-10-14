from __future__ import annotations

from domain.metadata.entities import Catalog
from domain.metadata.ports import CatalogRepository


class CreateCatalog:
    def __init__(self, repository: CatalogRepository):
        self._repository = repository

    def execute(self, project_id: str, name: str) -> Catalog:
        catalog = Catalog(project_id=project_id, name=name)
        self._repository.save_catalog(catalog)
        return catalog
