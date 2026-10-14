"""Adaptador real de `CredentialStore` sobre la librería `keyring`
(ítem 2 de la segunda evaluación de madurez post-8-etapas, ver
bitácora): usa el almacén seguro nativo del sistema operativo --
Windows Credential Locker, Keychain de macOS, o un Secret Service de
D-Bus en Linux (GNOME Keyring/KWallet) -- sin manejar el material
criptográfico ni el cifrado directamente: eso lo hace el backend del
sistema operativo, `keyring` solo es la capa de acceso multiplataforma.

Requiere un backend real disponible. En un entorno sin sesión gráfica
(headless) ni servicio de credenciales configurado -- exactamente este
entorno de construcción, confirmado: `keyring.get_keyring()` resuelve a
`keyring.backends.fail.Keyring`, que lanza `NoKeyringError` en cualquier
operación -- no hay backend real que probar. Mismo tipo de restricción
ya aceptada para `fastembed` (descarga de Hugging Face) y `tiktoken`
(descarga de la codificación): el diseño de `CredentialStore` como
capacidad opcional con manejo explícito de `CredentialStoreError`
existe precisamente para degradar con seguridad en este caso, no para
fingir que siempre hay un backend real."""
from __future__ import annotations

from typing import Optional

from domain.plugins.exceptions import CredentialStoreError
from domain.plugins.ports import CredentialStore

_DEFAULT_SERVICE_NAME = "ragstudio"


class KeyringCredentialStore(CredentialStore):
    def __init__(self, service_name: str = _DEFAULT_SERVICE_NAME):
        self._service_name = service_name

    def set_secret(self, key: str, value: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(self._service_name, key, value)
        except keyring.errors.KeyringError as exc:
            raise CredentialStoreError("guardar", str(exc)) from exc

    def get_secret(self, key: str) -> Optional[str]:
        import keyring
        import keyring.errors

        try:
            return keyring.get_password(self._service_name, key)
        except keyring.errors.KeyringError as exc:
            raise CredentialStoreError("leer", str(exc)) from exc

    def delete_secret(self, key: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(self._service_name, key)
        except keyring.errors.PasswordDeleteError:
            # keyring no distingue "la clave nunca existió" de "se borró
            # bien" -- ambos lanzan PasswordDeleteError en algunos
            # backends. delete_secret es idempotente por contrato del
            # puerto: si de verdad el backend está roto (no solo "no
            # existía"), la próxima llamada a set_secret/get_secret lo
            # va a reportar igual con CredentialStoreError.
            pass
        except keyring.errors.KeyringError as exc:
            raise CredentialStoreError("borrar", str(exc)) from exc
