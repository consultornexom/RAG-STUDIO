"""Dobles de prueba en memoria para el contexto Metadatos."""
from __future__ import annotations

from typing import Optional

from domain.metadata.entities import (
    Catalog, CatalogEntry, FieldDefinition, MetadataSchema, MetadataValueChange, SourceMetadataValue,
)
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository


class InMemoryMetadataSchemaRepository(MetadataSchemaRepository):
    def __init__(self):
        self._schemas: dict[str, MetadataSchema] = {}
        self._fields: dict[tuple[str, str], FieldDefinition] = {}

    def save_schema(self, schema: MetadataSchema) -> None:
        self._schemas[schema.id] = schema

    def get_active_schema(self, project_id: str) -> Optional[MetadataSchema]:
        return next(
            (s for s in self._schemas.values() if s.project_id == project_id and s.is_active), None
        )

    def save_field(self, project_id: str, field: FieldDefinition) -> None:
        self._fields[(field.schema_id, field.field_id)] = field

    def get_field(self, project_id: str, schema_id: str, field_id: str) -> Optional[FieldDefinition]:
        return self._fields.get((schema_id, field_id))

    def list_fields(self, project_id: str, schema_id: str) -> list[FieldDefinition]:
        return [f for (sid, _), f in self._fields.items() if sid == schema_id]

    def delete_field(self, project_id: str, schema_id: str, field_id: str) -> None:
        self._fields.pop((schema_id, field_id), None)


class InMemoryCatalogRepository(CatalogRepository):
    def __init__(self):
        self._catalogs: dict[str, Catalog] = {}
        self._entries: dict[str, list[CatalogEntry]] = {}

    def save_catalog(self, catalog: Catalog) -> None:
        self._catalogs[catalog.id] = catalog
        self._entries.setdefault(catalog.id, [])

    def get_catalog(self, project_id: str, catalog_id: str) -> Optional[Catalog]:
        return self._catalogs.get(catalog_id)

    def list_catalogs(self, project_id: str) -> list[Catalog]:
        return [c for c in self._catalogs.values() if c.project_id == project_id]

    def delete_catalog(self, project_id: str, catalog_id: str) -> None:
        self._catalogs.pop(catalog_id, None)
        self._entries.pop(catalog_id, None)

    def save_entry(self, project_id: str, entry: CatalogEntry) -> None:
        entries = self._entries.setdefault(entry.catalog_id, [])
        for i, existing in enumerate(entries):
            if existing.id == entry.id:
                entries[i] = entry
                return
        entries.append(entry)

    def list_entries(self, project_id: str, catalog_id: str) -> list[CatalogEntry]:
        return list(self._entries.get(catalog_id, []))

    def get_entry(self, project_id: str, catalog_id: str, value_code: str) -> Optional[CatalogEntry]:
        return next(
            (e for e in self._entries.get(catalog_id, []) if e.value_code == value_code), None
        )

    def delete_entry(self, project_id: str, catalog_id: str, entry_id: str) -> None:
        entries = self._entries.get(catalog_id, [])
        self._entries[catalog_id] = [e for e in entries if e.id != entry_id]


class InMemorySourceMetadataRepository(SourceMetadataRepository):
    def __init__(self):
        self._values: dict[tuple[str, str], SourceMetadataValue] = {}
        self._history: list[MetadataValueChange] = []

    def save_value(self, project_id: str, value: SourceMetadataValue) -> None:
        key = (value.source_id, value.field_id)
        existing = self._values.get(key)
        previous_value = existing.value if existing is not None else None
        if existing is None or previous_value != value.value:
            self._history.append(MetadataValueChange(
                source_id=value.source_id, field_id=value.field_id,
                previous_value=previous_value, new_value=value.value, changed_at=value.created_at,
            ))
        self._values[key] = value

    def list_value_history(
        self, project_id: str, source_id: str, field_id: Optional[str] = None,
    ) -> list[MetadataValueChange]:
        changes = [c for c in self._history if c.source_id == source_id]
        if field_id is not None:
            changes = [c for c in changes if c.field_id == field_id]
        return sorted(changes, key=lambda c: c.changed_at, reverse=True)

    def list_values_for_source(self, project_id: str, source_id: str) -> list[SourceMetadataValue]:
        return [v for (sid, _), v in self._values.items() if sid == source_id]

    def get_value(self, project_id: str, source_id: str, field_id: str) -> Optional[SourceMetadataValue]:
        return self._values.get((source_id, field_id))

    def delete_value(self, project_id: str, source_id: str, field_id: str) -> None:
        key = (source_id, field_id)
        existing = self._values.pop(key, None)
        if existing is not None:
            self._history.append(MetadataValueChange(
                source_id=source_id, field_id=field_id, previous_value=existing.value, new_value=None,
            ))

    def is_field_in_use(self, project_id: str, field_id: str) -> bool:
        return any(fid == field_id for _, fid in self._values.keys())
