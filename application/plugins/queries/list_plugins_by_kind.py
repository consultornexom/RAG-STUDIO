from __future__ import annotations

from domain.plugins.entities import Plugin, PluginKind
from domain.plugins.ports import PluginRepository


class ListPluginsByKind:
    def __init__(self, repository: PluginRepository):
        self._repository = repository

    def execute(self, kind: PluginKind) -> list[Plugin]:
        return self._repository.list_by_kind(PluginKind(kind))
