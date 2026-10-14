from __future__ import annotations

from domain.plugins.entities import Plugin
from domain.plugins.ports import PluginRepository


class ListPlugins:
    def __init__(self, repository: PluginRepository):
        self._repository = repository

    def execute(self) -> list[Plugin]:
        return self._repository.list_all()
