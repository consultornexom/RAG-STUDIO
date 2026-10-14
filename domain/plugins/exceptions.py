"""Excepciones del contexto Complementos."""
from __future__ import annotations


class PluginDomainError(Exception):
    """Base de las excepciones del contexto Complementos."""


class PluginNotFoundError(PluginDomainError):
    def __init__(self, plugin_id: str):
        super().__init__(f"No existe el complemento {plugin_id!r}.")


class DuplicatePluginCodeError(PluginDomainError):
    def __init__(self, kind: str, code: str):
        super().__init__(f"Ya existe un complemento de tipo {kind!r} con code={code!r}.")


class MissingEntryPointError(PluginDomainError):
    """Un complemento de tipo proveedor/importador/evaluador se
    registró sin `entry_point` -- solo una plantilla puede omitirlo,
    porque es datos, no código a cargar."""

    def __init__(self, kind: str, code: str):
        super().__init__(
            f"El complemento {code!r} (tipo {kind!r}) necesita entry_point: solo las "
            "plantillas pueden registrarse sin código que cargar."
        )


class PluginLoadError(PluginDomainError):
    """El `entry_point` de un complemento no se pudo importar, o la
    clase cargada no implementa el contrato esperado para su tipo."""

    def __init__(self, entry_point: str, reason: str):
        super().__init__(f"No se pudo cargar el complemento {entry_point!r}: {reason}")


class CredentialStoreError(PluginDomainError):
    """El almacén seguro de credenciales del sistema operativo no pudo
    guardar/leer/borrar un secreto (ítem 2 de la segunda evaluación de
    madurez post-8-etapas, ver bitácora). Típicamente porque no hay un
    backend real disponible en este equipo/sesión (Windows Credential
    Locker, Keychain de macOS, o un Secret Service de D-Bus en Linux
    -- este último requiere un daemon de sesión gráfica que no siempre
    está presente, p. ej. en un servidor sin escritorio). Quien captura
    esta excepción debe caer de vuelta a un comportamiento seguro (no
    guardar el secreto en texto plano en su lugar sin avisar), nunca
    ignorarla en silencio."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"El almacén seguro de credenciales del sistema operativo falló en "
            f"{operation!r}: {reason}"
        )
