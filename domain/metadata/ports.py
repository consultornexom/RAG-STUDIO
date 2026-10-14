"""Puertos del contexto Metadatos. Implementados en infrastructure.

project_id explícito en cada método por la misma razón que en
domain.documents.ports: el repositorio debe saber qué project.db abrir.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import Catalog, CatalogEntry, FieldDefinition, MetadataSchema, MetadataValueChange, SourceMetadataValue


class MetadataSchemaRepository(ABC):
    @abstractmethod
    def save_schema(self, schema: MetadataSchema) -> None: ...

    @abstractmethod
    def get_active_schema(self, project_id: str) -> Optional[MetadataSchema]: ...

    @abstractmethod
    def save_field(self, project_id: str, field: FieldDefinition) -> None: ...

    @abstractmethod
    def get_field(self, project_id: str, schema_id: str, field_id: str) -> Optional[FieldDefinition]: ...

    @abstractmethod
    def list_fields(self, project_id: str, schema_id: str) -> list[FieldDefinition]: ...

    @abstractmethod
    def delete_field(self, project_id: str, schema_id: str, field_id: str) -> None: ...


class CatalogRepository(ABC):
    @abstractmethod
    def save_catalog(self, catalog: Catalog) -> None: ...

    @abstractmethod
    def get_catalog(self, project_id: str, catalog_id: str) -> Optional[Catalog]: ...

    @abstractmethod
    def list_catalogs(self, project_id: str) -> list[Catalog]: ...

    @abstractmethod
    def delete_catalog(self, project_id: str, catalog_id: str) -> None: ...

    @abstractmethod
    def save_entry(self, project_id: str, entry: CatalogEntry) -> None: ...

    @abstractmethod
    def list_entries(self, project_id: str, catalog_id: str) -> list[CatalogEntry]: ...

    @abstractmethod
    def get_entry(self, project_id: str, catalog_id: str, value_code: str) -> Optional[CatalogEntry]: ...

    @abstractmethod
    def delete_entry(self, project_id: str, catalog_id: str, entry_id: str) -> None: ...


class SourceMetadataRepository(ABC):
    @abstractmethod
    def save_value(self, project_id: str, value: SourceMetadataValue) -> None: ...

    @abstractmethod
    def list_values_for_source(self, project_id: str, source_id: str) -> list[SourceMetadataValue]: ...

    @abstractmethod
    def get_value(self, project_id: str, source_id: str, field_id: str) -> Optional[SourceMetadataValue]: ...

    @abstractmethod
    def delete_value(self, project_id: str, source_id: str, field_id: str) -> None:
        """Desasocia el valor vigente de `field_id` para `source_id`
        (Ronda 6, punto 23 de Validacion_observaciones_RAG_STUDIO.md,
        hallazgo real de usuario: no había ninguna vía para esto, solo
        `save_value`, que siempre hace upsert). Debe registrar el
        cambio en el historial (`MetadataValueChange` con
        new_value=None) igual que `save_value`, para no perder rastro
        de auditoría; no lanza error si no había ningún valor
        guardado -- eso lo valida DeleteSourceMetadataValue antes de
        llamar aquí."""
        ...

    @abstractmethod
    def is_field_in_use(self, project_id: str, field_id: str) -> bool:
        """Ronda 3/4 (punto 12 de Validacion_observaciones_RAG_STUDIO.md):
        ¿alguna fuente del proyecto ya tiene un valor guardado para este
        field_id? Se agrega como una sola consulta de repositorio -- antes
        DeleteFieldDefinition respondía esto recorriendo
        list_for_project + list_values_for_source fuente por fuente,
        abriendo una conexión de base de datos nueva por cada una."""
        ...

    @abstractmethod
    def list_value_history(
        self, project_id: str, source_id: str, field_id: Optional[str] = None,
    ) -> list[MetadataValueChange]:
        """Historial de auditoría (ítem 5 de la evaluación de madurez
        post-8-etapas), más reciente primero. `save_value` debe
        agregar una entrada aquí cada vez que el valor vigente
        realmente cambia (ver docstring de MetadataValueChange) --
        `field_id=None` devuelve el historial de todos los campos de
        la fuente."""
        ...
