"""Caso de uso: editar un complemento ya registrado (Ronda 4, punto 3
de Validacion_observaciones_RAG_STUDIO.md).

Antes de esto, Complementos era el caso más profundo de "falta
edición": ni la interfaz ni la capa de aplicación ni el dominio tenían
ningún método para corregir un complemento después de registrarlo,
solo Registrar y Activar/Desactivar. `kind` y `code` no son editables
aquí -- son la llave con la que se busca un complemento
(`get_by_code`) y con la que se derivan las claves de credenciales
(`credential_key(code, ...)`); cambiarlos rompería esa relación, mismo
criterio ya aplicado a `FieldDefinition.field_id` y
`ChannelingScheme.code`. Reutiliza `register_plugin.externalize_secrets`
para que corregir un valor de configuración sensible (p. ej. una API
key) pase por el mismo camino que al registrar, en vez de duplicar esa
lógica.

Cuidado deliberado con los valores ya externalizados: `plugin.config`
tal como se lee de vuelta del repositorio ya trae
`CREDENTIAL_STORE_PLACEHOLDER` en los campos sensibles, no el secreto
real (nunca se persiste en texto plano -- ver
`ResolvePluginConfig`/README). Si quien llama (típicamente un
formulario de edición que precarga el config guardado) reenvía ese
config sin tocar esos campos, NO hay que volver a pasarlos por
`externalize_secrets`: guardaría el texto del marcador como si fuera el
secreto real, sobrescribiendo el secreto verdadero en el almacén
seguro. Por eso se separan aparte los campos que ya llegan con el
marcador y se reinsertan después, sin tocarlos."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from domain.plugins.entities import CREDENTIAL_STORE_PLACEHOLDER, Plugin
from domain.plugins.exceptions import MissingEntryPointError, PluginNotFoundError
from domain.plugins.ports import CredentialStore, PluginRepository

from .register_plugin import externalize_secrets


class UpdatePlugin:
    def __init__(self, repository: PluginRepository, credential_store: Optional[CredentialStore] = None):
        self._repository = repository
        self._credential_store = credential_store

    def execute(
        self, plugin_id: str, name: str, description: str = "", version: str = "0.1.0",
        entry_point: Optional[str] = None, config: Optional[dict[str, Any]] = None,
    ) -> Plugin:
        plugin = self._repository.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)

        config = dict(config or {})
        already_externalized = {k: v for k, v in config.items() if v == CREDENTIAL_STORE_PLACEHOLDER}
        to_externalize = {k: v for k, v in config.items() if k not in already_externalized}
        stored_config = externalize_secrets(self._credential_store, plugin.code, to_externalize)
        stored_config.update(already_externalized)
        updated = plugin.model_copy(update={
            "name": name, "description": description, "version": version,
            "entry_point": entry_point, "config": stored_config, "updated_at": datetime.now(timezone.utc),
        })
        if updated.requires_entry_point and updated.entry_point is None:
            raise MissingEntryPointError(updated.kind.value, updated.code)
        self._repository.save(updated)
        return updated
