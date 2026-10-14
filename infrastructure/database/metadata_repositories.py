"""Implementaciones concretas de MetadataSchemaRepository,
CatalogRepository y SourceMetadataRepository (ADR-001, sección 4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select

from domain.metadata.entities import (
    Catalog, CatalogEntry, FieldDataType, FieldDefinition, MetadataSchema, MetadataValueChange,
    SourceMetadataValue,
)
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import (
    CatalogEntryRecord, CatalogRecord, FieldDefinitionRecord, MetadataSchemaRecord, MetadataValueChangeRecord,
    SourceMetadataValueRecord,
)


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyMetadataSchemaRepository(MetadataSchemaRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save_schema(self, schema: MetadataSchema) -> None:
        with _session_factory_for(self._paths, schema.project_id)() as session:
            existing = session.get(MetadataSchemaRecord, schema.id)
            if existing is None:
                session.add(MetadataSchemaRecord(
                    id=schema.id, project_id=schema.project_id, version=schema.version,
                    is_active=schema.is_active, created_at=schema.created_at,
                ))
            else:
                existing.version = schema.version
                existing.is_active = schema.is_active
            session.commit()

    def get_active_schema(self, project_id: str) -> Optional[MetadataSchema]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(MetadataSchemaRecord).where(
                    MetadataSchemaRecord.project_id == project_id, MetadataSchemaRecord.is_active.is_(True)
                )
            ).scalars().first()
            if record is None:
                return None
            return MetadataSchema(
                id=record.id, project_id=record.project_id, version=record.version,
                is_active=record.is_active, created_at=record.created_at,
            )

    def save_field(self, project_id: str, field: FieldDefinition) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            key = (field.schema_id, field.field_id)
            existing = session.get(FieldDefinitionRecord, key)
            if existing is None:
                session.add(FieldDefinitionRecord(
                    schema_id=field.schema_id, field_id=field.field_id, display_name=field.display_name,
                    data_type=field.data_type.value, required=field.required, filterable=field.filterable,
                    multiple=field.multiple, inherited_by_chunks=field.inherited_by_chunks,
                    catalog_id=field.catalog_id, document_type_code=field.document_type_code,
                    created_at=field.created_at,
                ))
            else:
                existing.display_name = field.display_name
                existing.data_type = field.data_type.value
                existing.required = field.required
                existing.filterable = field.filterable
                existing.multiple = field.multiple
                existing.inherited_by_chunks = field.inherited_by_chunks
                existing.catalog_id = field.catalog_id
                existing.document_type_code = field.document_type_code
            session.commit()

    def get_field(self, project_id: str, schema_id: str, field_id: str) -> Optional[FieldDefinition]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(FieldDefinitionRecord, (schema_id, field_id))
            if record is None:
                return None
            return _record_to_field(record)

    def list_fields(self, project_id: str, schema_id: str) -> list[FieldDefinition]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(FieldDefinitionRecord).where(FieldDefinitionRecord.schema_id == schema_id)
            ).scalars().all()
            return [_record_to_field(r) for r in records]

    def delete_field(self, project_id: str, schema_id: str, field_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(FieldDefinitionRecord, (schema_id, field_id))
            if record is not None:
                session.delete(record)
                session.commit()


def _record_to_field(record: FieldDefinitionRecord) -> FieldDefinition:
    return FieldDefinition(
        field_id=record.field_id, schema_id=record.schema_id, display_name=record.display_name,
        data_type=FieldDataType(record.data_type), required=record.required, filterable=record.filterable,
        multiple=record.multiple, inherited_by_chunks=record.inherited_by_chunks,
        catalog_id=record.catalog_id, document_type_code=record.document_type_code,
        created_at=record.created_at,
    )


class SqlAlchemyCatalogRepository(CatalogRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save_catalog(self, catalog: Catalog) -> None:
        with _session_factory_for(self._paths, catalog.project_id)() as session:
            existing = session.get(CatalogRecord, catalog.id)
            if existing is None:
                session.add(CatalogRecord(
                    id=catalog.id, project_id=catalog.project_id, name=catalog.name,
                    created_at=catalog.created_at,
                ))
            else:
                existing.name = catalog.name
            session.commit()

    def get_catalog(self, project_id: str, catalog_id: str) -> Optional[Catalog]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(CatalogRecord, catalog_id)
            if record is None:
                return None
            return Catalog(
                id=record.id, project_id=record.project_id, name=record.name, created_at=record.created_at,
            )

    def list_catalogs(self, project_id: str) -> list[Catalog]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(CatalogRecord).where(CatalogRecord.project_id == project_id)
            ).scalars().all()
            return [
                Catalog(id=r.id, project_id=r.project_id, name=r.name, created_at=r.created_at)
                for r in records
            ]

    def delete_catalog(self, project_id: str, catalog_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            # SQLite no tiene FK con cascada configurada aquí: se borran
            # primero las entradas del catálogo para no dejar huérfanas.
            session.execute(
                delete(CatalogEntryRecord).where(CatalogEntryRecord.catalog_id == catalog_id)
            )
            record = session.get(CatalogRecord, catalog_id)
            if record is not None:
                session.delete(record)
            session.commit()

    def save_entry(self, project_id: str, entry: CatalogEntry) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            existing = session.get(CatalogEntryRecord, entry.id)
            if existing is None:
                session.add(CatalogEntryRecord(
                    id=entry.id, catalog_id=entry.catalog_id, value_code=entry.value_code,
                    label=entry.label, parent_entry_id=entry.parent_entry_id,
                ))
            else:
                existing.label = entry.label
                existing.parent_entry_id = entry.parent_entry_id
            session.commit()

    def list_entries(self, project_id: str, catalog_id: str) -> list[CatalogEntry]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(CatalogEntryRecord).where(CatalogEntryRecord.catalog_id == catalog_id)
            ).scalars().all()
            return [
                CatalogEntry(id=r.id, catalog_id=r.catalog_id, value_code=r.value_code,
                              label=r.label, parent_entry_id=r.parent_entry_id)
                for r in records
            ]

    def get_entry(self, project_id: str, catalog_id: str, value_code: str) -> Optional[CatalogEntry]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(CatalogEntryRecord).where(
                    CatalogEntryRecord.catalog_id == catalog_id, CatalogEntryRecord.value_code == value_code
                )
            ).scalars().first()
            if record is None:
                return None
            return CatalogEntry(id=record.id, catalog_id=record.catalog_id, value_code=record.value_code,
                                 label=record.label, parent_entry_id=record.parent_entry_id)

    def delete_entry(self, project_id: str, catalog_id: str, entry_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(CatalogEntryRecord, entry_id)
            if record is not None and record.catalog_id == catalog_id:
                session.delete(record)
                session.commit()


class SqlAlchemySourceMetadataRepository(SourceMetadataRepository):
    """save_value hace upsert por (source_id, field_id) -- solo el
    valor vigente, para lecturas rápidas -- y además agrega una
    entrada en metadata_value_change (tabla aparte, de solo inserción)
    cada vez que el valor realmente cambia, ver
    domain.metadata.entities.MetadataValueChange (ítem 5 de la
    evaluación de madurez post-8-etapas)."""

    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save_value(self, project_id: str, value: SourceMetadataValue) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            existing = session.execute(
                select(SourceMetadataValueRecord).where(
                    SourceMetadataValueRecord.source_id == value.source_id,
                    SourceMetadataValueRecord.field_id == value.field_id,
                )
            ).scalars().first()
            previous_value = existing.value if existing is not None else None
            if existing is None:
                session.add(SourceMetadataValueRecord(
                    id=value.id, source_id=value.source_id, field_id=value.field_id,
                    value=value.value, created_at=value.created_at,
                ))
            else:
                existing.value = value.value
                existing.created_at = value.created_at
            # Solo se registra en el historial cuando el valor
            # realmente cambia (creación con previous_value=None
            # cuenta como cambio) -- un guardado que repite el mismo
            # valor no debe generar ruido en la auditoría.
            if existing is None or previous_value != value.value:
                session.add(MetadataValueChangeRecord(
                    id=str(uuid.uuid4()), source_id=value.source_id, field_id=value.field_id,
                    previous_value=previous_value, new_value=value.value, changed_at=value.created_at,
                ))
            session.commit()

    def list_value_history(
        self, project_id: str, source_id: str, field_id: Optional[str] = None,
    ) -> list[MetadataValueChange]:
        with _session_factory_for(self._paths, project_id)() as session:
            query = select(MetadataValueChangeRecord).where(MetadataValueChangeRecord.source_id == source_id)
            if field_id is not None:
                query = query.where(MetadataValueChangeRecord.field_id == field_id)
            records = session.execute(
                query.order_by(MetadataValueChangeRecord.changed_at.desc())
            ).scalars().all()
            return [
                MetadataValueChange(
                    id=r.id, source_id=r.source_id, field_id=r.field_id,
                    previous_value=r.previous_value, new_value=r.new_value, changed_at=r.changed_at,
                )
                for r in records
            ]

    def list_values_for_source(self, project_id: str, source_id: str) -> list[SourceMetadataValue]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(SourceMetadataValueRecord).where(SourceMetadataValueRecord.source_id == source_id)
            ).scalars().all()
            return [
                SourceMetadataValue(id=r.id, source_id=r.source_id, field_id=r.field_id,
                                     value=r.value, created_at=r.created_at)
                for r in records
            ]

    def get_value(self, project_id: str, source_id: str, field_id: str) -> Optional[SourceMetadataValue]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(SourceMetadataValueRecord).where(
                    SourceMetadataValueRecord.source_id == source_id,
                    SourceMetadataValueRecord.field_id == field_id,
                )
            ).scalars().first()
            if record is None:
                return None
            return SourceMetadataValue(id=record.id, source_id=record.source_id, field_id=record.field_id,
                                        value=record.value, created_at=record.created_at)

    def delete_value(self, project_id: str, source_id: str, field_id: str) -> None:
        """Ronda 6, punto 23: a diferencia de save_value (upsert), esto
        borra de verdad la fila vigente -- y, igual que save_value,
        deja constancia en metadata_value_change (new_value=None) para
        no perder el rastro de auditoría."""
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(SourceMetadataValueRecord).where(
                    SourceMetadataValueRecord.source_id == source_id,
                    SourceMetadataValueRecord.field_id == field_id,
                )
            ).scalars().first()
            if record is None:
                return
            session.add(MetadataValueChangeRecord(
                id=str(uuid.uuid4()), source_id=source_id, field_id=field_id,
                previous_value=record.value, new_value=None, changed_at=datetime.now(timezone.utc),
            ))
            session.delete(record)
            session.commit()

    def is_field_in_use(self, project_id: str, field_id: str) -> bool:
        """Una sola conexión + una sola consulta (LIMIT 1), a diferencia
        de recorrer fuente por fuente desde la capa de aplicación (ver
        docstring en el puerto) -- el project.db ya tiene todos los
        valores de todas las fuentes del proyecto, no hace falta abrir
        una sesión por fuente para saberlo."""
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(SourceMetadataValueRecord.id).where(
                    SourceMetadataValueRecord.field_id == field_id
                ).limit(1)
            ).scalars().first()
            return record is not None
