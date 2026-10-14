"""Caso de uso: dar de baja (eliminar) un complemento registrado
(Ronda 4, punto 3 de Validacion_observaciones_RAG_STUDIO.md).

Se decidió que `PluginRepository.delete()` no necesita un bloqueo tipo
`*InUseError` (a diferencia de `DeleteFieldDefinition`,
`DeleteCatalogEntry`, `DeleteProject`, `DeleteTestCase`): un complemento
se busca en tiempo de ejecución por `kind`+`enabled`
(`PluginRepository.list_by_kind`, ver `RunEvaluation._load_custom_evaluators`),
nunca por un id de complemento guardado dentro de los datos de un
proyecto -- no hay una referencia huérfana posible que dejar atrás.

Lo que sí hay que limpiar es cualquier secreto externalizado al
`CredentialStore` del sistema operativo (ver
`register_plugin.externalize_secrets`): si no se borra, el secreto
queda huérfano en el almacén seguro, asociado a un `code` de complemento
que ya no existe. Se recorre `plugin.config` buscando claves sensibles
(`is_sensitive_config_key`) y se intenta borrar cada una vía
`credential_key(code, key)`; si el almacén no está disponible o el
secreto ya no estaba ahí, no es un error -- mismo criterio de
"mejor esfuerzo, sin romper la baja" que ya usa
`register_plugin.externalize_secrets` al guardar."""
from __future__ import annotations

from typing import Optional

from domain.plugins.entities import credential_key, is_sensitive_config_key
from domain.plugins.exceptions import CredentialStoreError, PluginNotFoundError
from domain.plugins.ports import CredentialStore, PluginRepository


class UnregisterPlugin:
    def __init__(self, repository: PluginRepository, credential_store: Optional[CredentialStore] = None):
        self._repository = repository
        self._credential_store = credential_store

    def execute(self, plugin_id: str) -> None:
        plugin = self._repository.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)

        if self._credential_store is not None:
            for key in plugin.config:
                if not is_sensitive_config_key(key):
                    continue
                try:
                    self._credential_store.delete_secret(credential_key(plugin.code, key))
                except CredentialStoreError:
                    continue

        self._repository.delete(plugin_id)
