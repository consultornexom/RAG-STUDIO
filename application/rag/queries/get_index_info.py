"""Consulta: estado vigente del indice vectorial de un proyecto."""
from __future__ import annotations

from typing import Optional

from domain.rag.entities import IndexInfo
from domain.rag.ports import IndexInfoRepository


class GetIndexInfo:
    def __init__(self, index_info_repository: IndexInfoRepository):
        self._index_info = index_info_repository

    def execute(self, project_id: str) -> Optional[IndexInfo]:
        return self._index_info.get(project_id)
