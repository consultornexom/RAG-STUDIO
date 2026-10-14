"""Puertos del contexto Complementos. Implementados en infrastructure
(ADR-001, sección 4). A diferencia de los demás puertos del proyecto,
`PluginRepository` no recibe `project_id`: el registro de complementos
es global (`application.db`), no por proyecto."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import Plugin, PluginKind


class PluginRepository(ABC):
    @abstractmethod
    def save(self, plugin: Plugin) -> None: ...

    @abstractmethod
    def get(self, plugin_id: str) -> Optional[Plugin]: ...

    @abstractmethod
    def get_by_code(self, kind: PluginKind, code: str) -> Optional[Plugin]: ...

    @abstractmethod
    def list_all(self) -> list[Plugin]: ...

    @abstractmethod
    def list_by_kind(self, kind: PluginKind) -> list[Plugin]: ...

    @abstractmethod
    def delete(self, plugin_id: str) -> None:
        """Ronda 4 (punto 3 de Validacion_observaciones_RAG_STUDIO.md):
        antes no existía ninguna forma de desregistrar un complemento,
        ni en la interfaz ni aquí en el dominio -- solo Registrar y
        Activar/Desactivar. A diferencia de campos de metadatos o
        entradas de catálogo, un Plugin no tiene ningún dato de
        proyecto que lo referencie por id (se consulta por kind+enabled
        en tiempo de ejecución, nunca por una relación guardada), así
        que el borrado no necesita bloquearse por "uso" -- ver
        UnregisterPlugin."""
        ...


class CredentialStore(ABC):
    """Puerto para guardar secretos (p. ej. una API key de un proveedor
    de embeddings/LLM externo, ver `Plugin.config`) en el almacén seguro
    de credenciales del sistema operativo, en vez de en texto plano
    dentro de `application.db` -- ítem 2 de la segunda evaluación de
    madurez post-8-etapas (ver bitácora), que cierra la brecha frente a
    ADR-001 sección 12 ("credenciales únicamente en el almacén seguro
    del sistema operativo; nunca en texto plano").

    Cualquier implementación debe lanzar `CredentialStoreError` (nunca
    dejar pasar una excepción cruda de una librería de terceros) cuando
    el backend real no esté disponible -- mismo criterio que
    `EmbeddingProviderError`/`TokenizerError` para dependencias externas
    con fallback: quien llama decide si degradar con seguridad (no
    guardar el secreto en texto plano sin avisar) o propagar el error."""

    @abstractmethod
    def set_secret(self, key: str, value: str) -> None: ...

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """Devuelve `None` si la clave nunca se guardó (no es lo mismo
        que un fallo del almacén, que lanza `CredentialStoreError`)."""
        ...

    @abstractmethod
    def delete_secret(self, key: str) -> None:
        """No debe fallar si la clave no existía (idempotente)."""
        ...


class CustomEvaluator(ABC):
    """Contrato que debe implementar un complemento de tipo
    `EVALUADOR`: un criterio de evaluación adicional para el banco de
    pruebas de Etapa 6, más allá de lo que `RunEvaluation` compara por
    defecto (intención, variables, acción, canalización, fuente).

    Alcance de esta iteración (ver README, "Limitaciones conocidas"):
    este contrato existe para que un complemento pueda registrarse y
    validarse (`PluginService.validate_plugin` verifica que la clase
    cargada en verdad implemente `evaluate`), pero `RunEvaluation`
    todavía no invoca evaluadores personalizados durante una corrida
    real -- integrarlo requeriría decidir cómo combinar su veredicto
    con los semáforos existentes, lo que queda para una iteración
    posterior si un caso real lo justifica."""

    @abstractmethod
    def evaluate(self, trace, test_case) -> tuple[bool, str]:
        """Recibe el `SimulationTrace` producido y el `TestCase`
        evaluado; devuelve (aprobado, motivo)."""
        ...
