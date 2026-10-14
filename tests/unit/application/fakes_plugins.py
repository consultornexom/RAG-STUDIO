"""Doble de prueba en memoria para el contexto Complementos."""
from __future__ import annotations

from typing import Optional

from domain.plugins.entities import Plugin, PluginKind
from domain.plugins.exceptions import CredentialStoreError
from domain.plugins.ports import CredentialStore, PluginRepository


class InMemoryPluginRepository(PluginRepository):
    def __init__(self):
        self._by_id: dict[str, Plugin] = {}

    def save(self, plugin: Plugin) -> None:
        self._by_id[plugin.id] = plugin

    def get(self, plugin_id: str) -> Optional[Plugin]:
        return self._by_id.get(plugin_id)

    def get_by_code(self, kind: PluginKind, code: str) -> Optional[Plugin]:
        return next(
            (p for p in self._by_id.values() if p.kind == kind and p.code == code), None
        )

    def list_all(self) -> list[Plugin]:
        return sorted(self._by_id.values(), key=lambda p: (p.kind.value, p.code))

    def list_by_kind(self, kind: PluginKind) -> list[Plugin]:
        return sorted(
            (p for p in self._by_id.values() if p.kind == kind), key=lambda p: p.code
        )

    def delete(self, plugin_id: str) -> None:
        self._by_id.pop(plugin_id, None)


class InMemoryCredentialStore(CredentialStore):
    """Doble de prueba de CredentialStore (ítem 2 de la segunda
    evaluación de madurez post-8-etapas): simula un almacén seguro real
    (Windows Credential Locker/Keychain/Secret Service) que sí funciona,
    a diferencia de `KeyringCredentialStore` en este entorno sin
    backend real (ver bitácora)."""

    def __init__(self):
        self._secrets: dict[str, str] = {}
        self.set_calls: list[tuple[str, str]] = []

    def set_secret(self, key: str, value: str) -> None:
        self.set_calls.append((key, value))
        self._secrets[key] = value

    def get_secret(self, key: str) -> Optional[str]:
        return self._secrets.get(key)

    def delete_secret(self, key: str) -> None:
        self._secrets.pop(key, None)


class FailingCredentialStore(CredentialStore):
    """Simula un almacén seguro no disponible (sin backend real -- ver
    `infrastructure.security.keyring_credential_store` en este entorno
    sin sesión gráfica/Secret Service) para probar que `RegisterPlugin`
    cae de vuelta a guardar config en texto plano sin romper el
    registro del complemento."""

    def set_secret(self, key: str, value: str) -> None:
        raise CredentialStoreError("guardar", "simulado: sin backend real disponible")

    def get_secret(self, key: str) -> Optional[str]:
        raise CredentialStoreError("leer", "simulado: sin backend real disponible")

    def delete_secret(self, key: str) -> None:
        raise CredentialStoreError("borrar", "simulado: sin backend real disponible")
