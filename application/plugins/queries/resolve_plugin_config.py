"""Resuelve de vuelta los valores sensibles de `Plugin.config` que
`RegisterPlugin`/`UpdatePlugin` externalizaron al almacén seguro de
credenciales (ítem 2 de la segunda evaluación de madurez post-8-etapas,
ver bitácora).

Uso previsto: quien en el futuro construya de verdad una instancia de
un complemento PROVEEDOR/IMPORTADOR a partir de su `entry_point` (hoy
`app/bootstrap.py` sigue construyendo los adaptadores reales a mano,
ver README) va a necesitar el valor real de una API key, no el
marcador `CREDENTIAL_STORE_PLACEHOLDER`. Sin `credential_store`
configurado, o si la clave nunca se guardó ahí (se quedó en texto plano
porque el almacén no estaba disponible al registrar -- ver
`register_plugin.externalize_secrets`), el placeholder se devuelve tal
cual: no hay nada que resolver, y no es un error."""
from __future__ import annotations

from typing import Any, Optional

from domain.plugins.entities import CREDENTIAL_STORE_PLACEHOLDER, Plugin, credential_key
from domain.plugins.exceptions import CredentialStoreError
from domain.plugins.ports import CredentialStore, PluginRepository


class ResolvePluginConfig:
    def __init__(self, repository: PluginRepository, credential_store: Optional[CredentialStore] = None):
        self._repository = repository
        self._credential_store = credential_store

    def execute(self, plugin: Plugin) -> dict[str, Any]:
        if self._credential_store is None:
            return dict(plugin.config)
        resolved = dict(plugin.config)
        for key, value in plugin.config.items():
            if value != CREDENTIAL_STORE_PLACEHOLDER:
                continue
            try:
                secret = self._credential_store.get_secret(credential_key(plugin.code, key))
            except CredentialStoreError:
                continue
            if secret is not None:
                resolved[key] = secret
        return resolved
