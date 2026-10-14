from __future__ import annotations

from datetime import datetime, timezone

from domain.plugins.entities import Plugin
from domain.plugins.exceptions import PluginNotFoundError
from domain.plugins.ports import PluginRepository


class SetPluginEnabled:
    def __init__(self, repository: PluginRepository):
        self._repository = repository

    def execute(self, plugin_id: str, enabled: bool) -> Plugin:
        plugin = self._repository.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)
        updated = plugin.model_copy(update={"enabled": enabled, "updated_at": datetime.now(timezone.utc)})
        self._repository.save(updated)
        return updated
