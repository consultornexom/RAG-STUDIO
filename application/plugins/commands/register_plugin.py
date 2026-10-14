from __future__ import annotations

import logging
from typing import Any, Optional

from domain.plugins.entities import (
    CREDENTIAL_STORE_PLACEHOLDER, Plugin, PluginKind, credential_key, is_sensitive_config_key,
)
from domain.plugins.exceptions import CredentialStoreError, DuplicatePluginCodeError, MissingEntryPointError
from domain.plugins.ports import CredentialStore, PluginRepository

logger = logging.getLogger(__name__)


def externalize_secrets(
    credential_store: Optional[CredentialStore], code: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Mueve cada valor de `config` cuya clave parezca sensible
    (`is_sensitive_config_key` -- ítem 2 de la segunda evaluación de
    madurez post-8-etapas, ver bitácora) al almacén seguro de
    credenciales del sistema operativo, dejando
    `CREDENTIAL_STORE_PLACEHOLDER` en su lugar dentro de lo que se
    persiste en `application.db`: así `Plugin.config` sigue indicando
    que el campo tiene un valor configurado, sin exponerlo en texto
    plano.

    Sin `credential_store` configurado, o si el almacén falla (sin
    backend real disponible -- ver
    `infrastructure.security.keyring_credential_store`), el valor se
    deja tal como llegó (texto plano): es el comportamiento de antes de
    este ítem, no una regresión silenciosa nueva, y queda una
    advertencia en el log para que no pase inadvertido.

    Función de módulo (no método) desde la Ronda 4 (punto 3 de
    Validacion_observaciones_RAG_STUDIO.md): la usan tanto
    RegisterPlugin como UpdatePlugin, y duplicarla entre ambos hubiera
    sido el mismo tipo de descuido que ya se corrigió en otros
    contextos (una sola fuente de verdad para "cómo se guarda un
    secreto de plugin", en vez de dos copias que puedan divergir)."""
    if credential_store is None:
        return config
    result = dict(config)
    for key, value in config.items():
        if not is_sensitive_config_key(key) or not isinstance(value, str) or not value:
            continue
        try:
            credential_store.set_secret(credential_key(code, key), value)
        except CredentialStoreError as exc:
            logger.warning(
                "No se pudo guardar el campo de configuracion '%s' del complemento "
                "'%s' en el almacen seguro de credenciales (%s); se guarda sin "
                "cifrar en application.db, igual que antes de este item.",
                key, code, exc,
            )
            continue
        result[key] = CREDENTIAL_STORE_PLACEHOLDER
    return result


class RegisterPlugin:
    def __init__(self, repository: PluginRepository, credential_store: Optional[CredentialStore] = None):
        self._repository = repository
        self._credential_store = credential_store

    def execute(
        self, kind: PluginKind, code: str, name: str, description: str = "", version: str = "0.1.0",
        entry_point: Optional[str] = None, config: Optional[dict[str, Any]] = None,
    ) -> Plugin:
        # kind puede llegar como PluginKind (llamadas internas/pruebas) o
        # como string plano (la UI, que nunca importa domain -- ADR-001);
        # se normaliza aquí, antes de usarlo para consultar el repositorio.
        kind = PluginKind(kind)
        if self._repository.get_by_code(kind, code) is not None:
            raise DuplicatePluginCodeError(kind.value, code)
        stored_config = externalize_secrets(self._credential_store, code, dict(config or {}))
        plugin = Plugin(
            kind=kind, code=code, name=name, description=description, version=version,
            entry_point=entry_point, config=stored_config,
        )
        if plugin.requires_entry_point and plugin.entry_point is None:
            raise MissingEntryPointError(plugin.kind.value, plugin.code)
        self._repository.save(plugin)
        return plugin
