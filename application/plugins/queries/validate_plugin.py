"""Intenta cargar el `entry_point` de un complemento y reporta el
resultado -- nunca invoca la lógica de negocio del complemento en sí
(no llama a `embed_texts`/`extract`/`evaluate`), solo confirma que la
clase se puede importar y que implementa el contrato esperado para su
tipo. Es la validación que un usuario puede correr después de instalar
un complemento nuevo, antes de confiar en él."""
from __future__ import annotations

from typing import Any

from domain.plugins.exceptions import PluginNotFoundError, PluginLoadError
from domain.plugins.loader import load_and_validate
from domain.plugins.ports import PluginRepository


class ValidatePlugin:
    def __init__(self, repository: PluginRepository):
        self._repository = repository

    def execute(self, plugin_id: str) -> dict[str, Any]:
        plugin = self._repository.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)
        try:
            loaded = load_and_validate(plugin)
        except PluginLoadError as exc:
            return {"ok": False, "message": str(exc)}
        if plugin.entry_point is None:
            return {"ok": True, "message": "Plantilla: no requiere código, solo datos de configuración."}
        return {"ok": True, "message": f"Se cargó y valida correctamente: {loaded.__module__}.{loaded.__name__}"}
