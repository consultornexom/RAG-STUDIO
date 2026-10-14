"""Fachada de application para el contexto Complementos (Etapa 8).

A diferencia de todas las demás fachadas del proyecto, sus métodos no
reciben `project_id`: el registro de complementos es global a la
instalación (`application.db`), no por proyecto."""
from __future__ import annotations

from typing import Any, Optional

from domain.plugins.entities import Plugin, PluginKind
from domain.plugins.ports import CredentialStore, PluginRepository

from .commands.register_plugin import RegisterPlugin
from .commands.set_plugin_enabled import SetPluginEnabled
from .commands.unregister_plugin import UnregisterPlugin
from .commands.update_plugin import UpdatePlugin
from .queries.get_plugin import GetPlugin
from .queries.list_plugins import ListPlugins
from .queries.list_plugins_by_kind import ListPluginsByKind
from .queries.resolve_plugin_config import ResolvePluginConfig
from .queries.validate_plugin import ValidatePlugin


class PluginService:
    def __init__(self, plugin_repository: PluginRepository, credential_store: Optional[CredentialStore] = None):
        self._register = RegisterPlugin(plugin_repository, credential_store=credential_store)
        self._update = UpdatePlugin(plugin_repository, credential_store=credential_store)
        self._unregister = UnregisterPlugin(plugin_repository, credential_store=credential_store)
        self._set_enabled = SetPluginEnabled(plugin_repository)
        self._list_all = ListPlugins(plugin_repository)
        self._list_by_kind = ListPluginsByKind(plugin_repository)
        self._get = GetPlugin(plugin_repository)
        self._validate = ValidatePlugin(plugin_repository)
        self._resolve_config = ResolvePluginConfig(plugin_repository, credential_store=credential_store)

    def register_plugin(
        self, kind: PluginKind, code: str, name: str, description: str = "", version: str = "0.1.0",
        entry_point: Optional[str] = None, config: Optional[dict[str, Any]] = None,
    ) -> Plugin:
        return self._register.execute(
            kind, code, name, description=description, version=version, entry_point=entry_point, config=config,
        )

    def update_plugin(
        self, plugin_id: str, name: str, description: str = "", version: str = "0.1.0",
        entry_point: Optional[str] = None, config: Optional[dict[str, Any]] = None,
    ) -> Plugin:
        return self._update.execute(
            plugin_id, name, description=description, version=version, entry_point=entry_point, config=config,
        )

    def unregister_plugin(self, plugin_id: str) -> None:
        self._unregister.execute(plugin_id)

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> Plugin:
        return self._set_enabled.execute(plugin_id, enabled)

    def list_plugins(self) -> list[Plugin]:
        return self._list_all.execute()

    def list_plugins_by_kind(self, kind: PluginKind) -> list[Plugin]:
        return self._list_by_kind.execute(kind)

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        return self._get.execute(plugin_id)

    def validate_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self._validate.execute(plugin_id)

    def resolve_plugin_config(self, plugin: Plugin) -> dict[str, Any]:
        """Devuelve `plugin.config` con los valores sensibles resueltos
        de vuelta desde el almacén seguro de credenciales (ítem 2 de la
        segunda evaluación de madurez post-8-etapas, ver bitácora) --
        para quien construya de verdad una instancia del complemento."""
        return self._resolve_config.execute(plugin)
