from __future__ import annotations

from typing import Optional

from domain.plugins.entities import Plugin
from domain.plugins.ports import PluginRepository


class GetPlugin:
    def __init__(self, repository: PluginRepository):
        self._repository = repository

    def execute(self, plugin_id: str) -> Optional[Plugin]:
        return self._repository.get(plugin_id)
