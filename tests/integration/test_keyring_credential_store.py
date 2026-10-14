"""Prueba de integración real de KeyringCredentialStore -- contra la
librería `keyring` de verdad, no un doble (ítem 2 de la segunda
evaluación de madurez post-8-etapas).

Requiere un backend real del sistema operativo (Windows Credential
Locker, Keychain de macOS, o un Secret Service de D-Bus en Linux --
mismo patrón que FastEmbedEmbeddingProvider/TiktokenCounter para
dependencias externas): en un entorno sin ese backend (headless, sin
sesión gráfica ni daemon de credenciales -- confirmado en este entorno
de construcción: `keyring.get_keyring()` resuelve a
`keyring.backends.fail.Keyring`), estas pruebas se omiten
explícitamente con un motivo claro en vez de fallar en rojo. En la
máquina real del usuario, con un backend real disponible, se ejecutan
y validan de verdad."""
from __future__ import annotations

import pytest

from domain.plugins.exceptions import CredentialStoreError
from infrastructure.security.keyring_credential_store import KeyringCredentialStore


def _skip_if_no_backend(exc: CredentialStoreError) -> None:
    pytest.skip(f"keyring no tiene un backend real disponible en este entorno: {exc}")


@pytest.fixture
def real_store():
    return KeyringCredentialStore(service_name="ragstudio-pytest")


def test_set_and_get_secret_round_trips_through_the_real_os_store(real_store):
    try:
        real_store.set_secret("clave-de-prueba", "valor-secreto")
        value = real_store.get_secret("clave-de-prueba")
    except CredentialStoreError as exc:
        _skip_if_no_backend(exc)
        return
    try:
        assert value == "valor-secreto"
    finally:
        real_store.delete_secret("clave-de-prueba")


def test_get_secret_returns_none_for_a_key_that_was_never_stored(real_store):
    try:
        value = real_store.get_secret("clave-que-nunca-existio")
    except CredentialStoreError as exc:
        _skip_if_no_backend(exc)
        return
    assert value is None


def test_delete_secret_is_idempotent(real_store):
    try:
        real_store.set_secret("clave-a-borrar", "x")
        real_store.delete_secret("clave-a-borrar")
        real_store.delete_secret("clave-a-borrar")  # segunda vez: no debe fallar
    except CredentialStoreError as exc:
        _skip_if_no_backend(exc)
        return


# ---------- rutas sin backend real (no requieren un almacén de SO) ----------

def test_set_secret_raises_credential_store_error_when_backend_unavailable(monkeypatch):
    import keyring
    import keyring.errors

    store = KeyringCredentialStore(service_name="ragstudio-pytest")

    def _fake_set_password(service, key, value):
        raise keyring.errors.NoKeyringError("simulado: sin backend real disponible")

    monkeypatch.setattr(keyring, "set_password", _fake_set_password)
    with pytest.raises(CredentialStoreError):
        store.set_secret("x", "y")


def test_get_secret_raises_credential_store_error_when_backend_unavailable(monkeypatch):
    import keyring
    import keyring.errors

    store = KeyringCredentialStore(service_name="ragstudio-pytest")

    def _fake_get_password(service, key):
        raise keyring.errors.NoKeyringError("simulado: sin backend real disponible")

    monkeypatch.setattr(keyring, "get_password", _fake_get_password)
    with pytest.raises(CredentialStoreError):
        store.get_secret("x")


def test_delete_secret_swallows_password_delete_error_but_not_other_keyring_errors(monkeypatch):
    import keyring
    import keyring.errors

    store = KeyringCredentialStore(service_name="ragstudio-pytest")

    def _fake_delete_password_not_found(service, key):
        raise keyring.errors.PasswordDeleteError("no existe")

    monkeypatch.setattr(keyring, "delete_password", _fake_delete_password_not_found)
    store.delete_secret("x")  # no debe lanzar: idempotente

    def _fake_delete_password_broken_backend(service, key):
        raise keyring.errors.NoKeyringError("simulado: sin backend real disponible")

    monkeypatch.setattr(keyring, "delete_password", _fake_delete_password_broken_backend)
    with pytest.raises(CredentialStoreError):
        store.delete_secret("x")
