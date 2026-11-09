"""Fachada de application para el contexto Metadatos."""
from __future__ import annotations

from typing import Optional

from domain.documents.ports import SourceRepository
from domain.metadata.entities import (
    Catalog, CatalogEntry, FieldDefinition, MetadataSchema, MetadataValueChange, SourceMetadataValue,
    fields_applicable_to,
)
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository

from .commands.add_catalog_entry import AddCatalogEntry
from .commands.add_field_definition import AddFieldDefinition
from .commands.bulk_set_source_metadata_value import BulkSetSourceMetadataValue, BulkSetSourceMetadataValueResult
from .commands.create_catalog import CreateCatalog
from .commands.create_metadata_schema import CreateMetadataSchema
from .commands.delete_catalog import DeleteCatalog
from .commands.delete_catalog_entry import DeleteCatalogEntry
from .commands.delete_field_definition import DeleteFieldDefinition
from .commands.delete_source_metadata_value import DeleteSourceMetadataValue
from .commands.remove_source_metadata_value_item import RemoveSourceMetadataValueItem
from .commands.set_source_metadata_value import SetSourceMetadataValue, ValueAssignmentMode
from .commands.update_catalog import UpdateCatalog
from .commands.update_catalog_entry import UpdateCatalogEntry
from .commands.update_field_definition import UpdateFieldDefinition
from .queries.get_coverage_report import GetSourceMetadataCoverageReport
from .queries.get_metadata_schema import GetMetadataSchema
from .queries.list_catalog_entries import ListCatalogEntries
from .queries.list_catalogs import ListCatalogs
from .queries.list_source_metadata_values import ListSourceMetadataValues
from .queries.list_value_history import ListMetadataValueHistory


class MetadataService:
    def __init__(
        self,
        schema_repository: MetadataSchemaRepository,
        catalog_repository: CatalogRepository,
        source_metadata_repository: SourceMetadataRepository,
        source_repository: SourceRepository,
    ):
        self._create_schema = CreateMetadataSchema(schema_repository)
        self._add_field = AddFieldDefinition(schema_repository, catalog_repository)
        self._update_field = UpdateFieldDefinition(schema_repository, catalog_repository)
        self._delete_field = DeleteFieldDefinition(schema_repository, source_metadata_repository)
        self._create_catalog = CreateCatalog(catalog_repository)
        self._update_catalog = UpdateCatalog(catalog_repository)
        self._delete_catalog = DeleteCatalog(catalog_repository, schema_repository)
        self._add_entry = AddCatalogEntry(catalog_repository)
        self._update_entry = UpdateCatalogEntry(
            catalog_repository, schema_repository, source_repository, source_metadata_repository
        )
        self._delete_entry = DeleteCatalogEntry(
            catalog_repository, schema_repository, source_repository, source_metadata_repository
        )
        self._set_value = SetSourceMetadataValue(schema_repository, catalog_repository, source_metadata_repository)
        self._bulk_set_value = BulkSetSourceMetadataValue(
            schema_repository, catalog_repository, source_metadata_repository, source_repository
        )
        self._delete_value = DeleteSourceMetadataValue(source_metadata_repository)
        self._remove_value_item = RemoveSourceMetadataValueItem(schema_repository, source_metadata_repository)
        self._get_schema = GetMetadataSchema(schema_repository)
        self._list_catalogs = ListCatalogs(catalog_repository)
        self._list_entries = ListCatalogEntries(catalog_repository)
        self._coverage = GetSourceMetadataCoverageReport(
            source_repository, schema_repository, source_metadata_repository
        )
        self._list_source_values = ListSourceMetadataValues(source_metadata_repository)
        self._list_value_history = ListMetadataValueHistory(source_metadata_repository)

    def create_schema(self, project_id: str) -> MetadataSchema:
        return self._create_schema.execute(project_id)

    def add_field_definition(
        self, project_id: str, schema_id: str, field_id: str, display_name: str, data_type, **kwargs
    ) -> FieldDefinition:
        return self._add_field.execute(project_id, schema_id, field_id, display_name, data_type, **kwargs)

    def update_field_definition(
        self, project_id: str, schema_id: str, field_id: str, display_name: str, **kwargs
    ) -> FieldDefinition:
        return self._update_field.execute(project_id, schema_id, field_id, display_name, **kwargs)

    def delete_field_definition(self, project_id: str, schema_id: str, field_id: str) -> None:
        self._delete_field.execute(project_id, schema_id, field_id)

    def create_catalog(self, project_id: str, name: str) -> Catalog:
        return self._create_catalog.execute(project_id, name)

    def update_catalog(self, project_id: str, catalog_id: str, name: str) -> Catalog:
        return self._update_catalog.execute(project_id, catalog_id, name)

    def delete_catalog(self, project_id: str, catalog_id: str) -> None:
        self._delete_catalog.execute(project_id, catalog_id)

    def list_catalogs(self, project_id: str) -> list[Catalog]:
        return self._list_catalogs.execute(project_id)

    def add_catalog_entry(
        self, project_id: str, catalog_id: str, value_code: str, label: str, parent_entry_id=None
    ) -> CatalogEntry:
        return self._add_entry.execute(project_id, catalog_id, value_code, label, parent_entry_id)

    def update_catalog_entry(
        self, project_id: str, catalog_id: str, entry_id: str, label: str, parent_entry_id=None,
        value_code: Optional[str] = None,
    ) -> CatalogEntry:
        """`value_code` (Ronda 3, punto 13) solo puede cambiar mientras
        ninguna fuente ya tenga el código actual guardado -- ver
        UpdateCatalogEntry/CatalogEntryInUseError."""
        return self._update_entry.execute(project_id, catalog_id, entry_id, label, parent_entry_id, value_code)

    def delete_catalog_entry(self, project_id: str, catalog_id: str, entry_id: str) -> None:
        self._delete_entry.execute(project_id, catalog_id, entry_id)

    def set_source_metadata_value(
        self, project_id: str, schema_id: str, source_id: str, field_id: str, raw_value,
        mode: object = ValueAssignmentMode.REEMPLAZAR,
    ) -> None:
        """Ronda 97: `mode="agregar"` suma los valores a los que ya tiene la
        fuente (solo campos de varios valores); "reemplazar" (por defecto)
        deja exactamente los indicados -- ver SetSourceMetadataValue."""
        self._set_value.execute(project_id, schema_id, source_id, field_id, raw_value, mode)

    def bulk_set_source_metadata_value(
        self, project_id: str, schema_id: str, source_ids: list[str], field_id: str, raw_value,
        mode: object = ValueAssignmentMode.REEMPLAZAR,
    ) -> BulkSetSourceMetadataValueResult:
        """Ronda 5, punto 21: asigna el mismo valor de `field_id` a
        varias fuentes de una vez. Un valor/campo inválido aborta todo
        el lote (error de diseño, no de una fuente puntual); una
        fuente inexistente solo se omite -- ver
        BulkSetSourceMetadataValue."""
        return self._bulk_set_value.execute(project_id, schema_id, source_ids, field_id, raw_value, mode)

    def delete_source_metadata_value(self, project_id: str, source_id: str, field_id: str) -> None:
        """Ronda 6, punto 23: desasocia el valor de `field_id` guardado
        para `source_id`. Lanza SourceMetadataValueNotFoundError si no
        había ningún valor asignado -- ver DeleteSourceMetadataValue."""
        self._delete_value.execute(project_id, source_id, field_id)

    def remove_source_metadata_value_item(
        self, project_id: str, schema_id: str, source_id: str, field_id: str, item: str,
    ) -> list[str]:
        """Ronda 97: quita UN valor de un campo de varios valores y conserva
        los demás; devuelve los que quedan -- ver RemoveSourceMetadataValueItem."""
        return self._remove_value_item.execute(project_id, schema_id, source_id, field_id, item)

    def get_schema(self, project_id: str):
        return self._get_schema.execute(project_id)

    def list_applicable_fields(self, project_id: str, document_type_code: str) -> list[FieldDefinition]:
        """Campos del esquema activo que aplican a una fuente con este
        document_type_code (genéricos + los de su mismo tipo) -- ver
        domain.metadata.entities.fields_applicable_to. Punto 10 de
        Validacion_observaciones_RAG_STUDIO.md: la usa "Valores por
        fuente" (ui/metadata/panel.py) para no ofrecer capturar campos
        de un tipo de documento distinto al de la fuente activa. UI
        nunca importa domain directamente (ADR-001, sección 4), por
        eso este método vive aquí en vez de que ui/metadata/panel.py
        llame a fields_applicable_to por su cuenta."""
        _, fields = self.get_schema(project_id)
        return fields_applicable_to(fields, document_type_code)

    def list_catalog_entries(self, project_id: str, catalog_id: str) -> list[CatalogEntry]:
        return self._list_entries.execute(project_id, catalog_id)

    def get_coverage_report(self, project_id: str) -> dict:
        return self._coverage.execute(project_id)

    def list_source_metadata_values(self, project_id: str, source_id: str) -> list[SourceMetadataValue]:
        return self._list_source_values.execute(project_id, source_id)

    def list_value_history(
        self, project_id: str, source_id: str, field_id: Optional[str] = None,
    ) -> list[MetadataValueChange]:
        return self._list_value_history.execute(project_id, source_id, field_id)
