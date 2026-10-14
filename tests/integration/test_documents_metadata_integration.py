"""Integración real (SQLite) del gobierno documental de Etapa 2:
inventario de fuentes + metamodelo de metadatos, incluyendo su
portabilidad automática dentro de .agentproj."""
from __future__ import annotations

from pathlib import Path

import pytest

from application.documents.service import DocumentService
from application.metadata.service import MetadataService
from application.projects.service import ProjectService
from domain.documents.entities import SourceType, SourceValidationStatus
from domain.metadata.entities import FieldDataType
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyExtractionRepository
from infrastructure.database.metadata_repositories import (
    SqlAlchemyCatalogRepository, SqlAlchemyMetadataSchemaRepository, SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.repositories import SqlAlchemyConfigurationRepository, SqlAlchemyProjectRepository
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths


def _bootstrap_services(base_dir: Path):
    paths = InstallationPaths(base_dir)
    paths.ensure_installation_layout()

    source_repository = SqlAlchemySourceRepository(paths)
    project_service = ProjectService(
        SqlAlchemyProjectRepository(paths), SqlAlchemyConfigurationRepository(paths),
        FilesystemProjectPackager(paths), source_repository,
    )
    document_service = DocumentService(source_repository, SqlAlchemyExtractionRepository(paths))
    metadata_service = MetadataService(
        SqlAlchemyMetadataSchemaRepository(paths), SqlAlchemyCatalogRepository(paths),
        SqlAlchemySourceMetadataRepository(paths), source_repository,
    )
    return project_service, document_service, metadata_service, paths


def test_full_governance_flow_persists_and_validates(tmp_path):
    project_service, document_service, metadata_service, _ = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Agente universitario")

    schema = metadata_service.create_schema(project.id)
    catalog = metadata_service.create_catalog(project.id, "Planteles")
    metadata_service.add_catalog_entry(project.id, catalog.id, "MERIDA", "Mérida")
    metadata_service.add_field_definition(
        project.id, schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO,
        catalog_id=catalog.id, required=True, filterable=True, inherited_by_chunks=True,
    )

    source = document_service.register_source(project.id, "Ficha del programa", SourceType.PDF)
    metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "campus_id", "MERIDA")

    source = document_service.update_validation_status(
        project.id, source.id, SourceValidationStatus.EN_REVISION
    )
    source = document_service.update_validation_status(
        project.id, source.id, SourceValidationStatus.VALIDADO
    )
    assert source.is_usable_for_responses()

    report = metadata_service.get_coverage_report(project.id)
    assert report["coverage_ratio"] == 1.0
    assert report["meets_acceptance_threshold"] is True


# ---------- get_source_lineage contra SQLite real (Pista C.2b del ADR-003) ----------

def test_get_source_lineage_walks_the_full_chain_against_real_persistence(tmp_path):
    project_service, document_service, _metadata_service, _paths = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Agente con reglamentos versionados")

    v1 = document_service.register_source(project.id, "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    v2 = document_service.register_source(
        project.id, "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=v1.id,
    )
    v3 = document_service.register_source(
        project.id, "Reglamento v3", SourceType.PDF, content_hash="hash-3", supersedes_source_id=v2.id,
    )

    # Pedido desde cualquier eslabón -- incluido el más viejo, el
    # sentido que antes no se podía recorrer -- debe devolver la
    # cadena completa, de la más antigua a la más nueva.
    for source_id in (v1.id, v2.id, v3.id):
        lineage = document_service.get_source_lineage(project.id, source_id)
        assert [s.id for s in lineage] == [v1.id, v2.id, v3.id]


# ---------- delete_field_definition / is_field_in_use contra SQLite real (Ronda 3/4, punto 12) ----------

def test_delete_field_in_use_is_detected_with_single_query_path(tmp_path):
    # Ejercita infrastructure.database.metadata_repositories.
    # SqlAlchemySourceMetadataRepository.is_field_in_use contra un
    # project.db real -- la consulta que reemplazó el recorrido fuente
    # por fuente de DeleteFieldDefinition (mejora 6, Ronda 3/4).
    from domain.metadata.exceptions import FieldInUseError

    project_service, document_service, metadata_service, _ = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Agente con metadatos")
    schema = metadata_service.create_schema(project.id)
    metadata_service.add_field_definition(project.id, schema.id, "titulo", "Título", FieldDataType.TEXTO)
    source = document_service.register_source(project.id, "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "titulo", "Reglamento 2026")

    with pytest.raises(FieldInUseError):
        metadata_service.delete_field_definition(project.id, schema.id, "titulo")

    # un campo nunca usado sigue pudiendo eliminarse sin problema
    metadata_service.add_field_definition(project.id, schema.id, "nota", "Nota", FieldDataType.TEXTO)
    metadata_service.delete_field_definition(project.id, schema.id, "nota")
    _, fields = metadata_service.get_schema(project.id)
    assert {f.field_id for f in fields} == {"titulo"}


# ---------- delete_project real contra SQLite + filesystem (Ronda 3, punto 13) ----------

def test_delete_project_removes_project_directory(tmp_path):
    project_service, _, _, paths = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Proyecto vacío creado por error")
    project_dir = paths.project_dir(project.id)
    assert project_dir.exists()

    project_service.delete_project(project.id)

    assert not project_dir.exists()
    assert project.id not in {p.id for p in project_service.list_projects()}


def test_delete_project_with_sources_is_blocked_and_keeps_directory(tmp_path):
    from domain.projects.exceptions import ProjectInUseError

    project_service, document_service, _, paths = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Proyecto con fuentes")
    document_service.register_source(project.id, "Reglamento", SourceType.PDF)

    with pytest.raises(ProjectInUseError):
        project_service.delete_project(project.id)

    assert paths.project_dir(project.id).exists()
    assert project.id in {p.id for p in project_service.list_projects()}


def test_documents_and_metadata_survive_export_import_roundtrip(tmp_path):
    project_service, document_service, metadata_service, paths_a = _bootstrap_services(tmp_path / "laptop_a")
    project = project_service.create_project("Agente con fuentes")

    schema = metadata_service.create_schema(project.id)
    catalog = metadata_service.create_catalog(project.id, "Temas")
    metadata_service.add_catalog_entry(project.id, catalog.id, "BECAS", "Becas")
    metadata_service.add_field_definition(
        project.id, schema.id, "topic", "Tema", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source = document_service.register_source(project.id, "Reglamento de becas", SourceType.PDF)
    metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "topic", "BECAS")

    export_path = tmp_path / "export.agentproj"
    project_service.export_project(project.id, str(export_path))

    project_service_b, document_service_b, metadata_service_b, _ = _bootstrap_services(tmp_path / "laptop_b")
    imported = project_service_b.import_project(str(export_path))

    imported_sources = document_service_b.list_sources(imported.id)
    assert len(imported_sources) == 1
    assert imported_sources[0].title == "Reglamento de becas"

    imported_schema, imported_fields = metadata_service_b.get_schema(imported.id)
    assert imported_schema.id == schema.id
    assert {f.field_id for f in imported_fields} == {"topic"}

    entries = metadata_service_b.list_catalog_entries(imported.id, catalog.id)
    assert {e.value_code for e in entries} == {"BECAS"}


def test_metadata_value_history_persists_real_changes_in_project_db(tmp_path):
    # Ítem 5 de la evaluación de madurez post-8-etapas: verifica el
    # historial de auditoría contra SQLite real (Alembic), no solo
    # contra el doble en memoria.
    project_service, document_service, metadata_service, _ = _bootstrap_services(tmp_path / "laptop")
    project = project_service.create_project("Agente con historial")

    schema = metadata_service.create_schema(project.id)
    metadata_service.add_field_definition(project.id, schema.id, "topic", "Tema", FieldDataType.TEXTO)
    source = document_service.register_source(project.id, "Ficha", SourceType.PDF)

    metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "topic", "becas")
    metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "topic", "admisiones")

    history = metadata_service.list_value_history(project.id, source.id)
    assert [h.new_value for h in history] == ["admisiones", "becas"]
    assert history[0].previous_value == "becas"
    assert history[1].previous_value is None

    # El valor vigente sigue siendo upsert -- una sola fila real en
    # source_metadata_value, sin importar cuántas entradas de
    # historial se acumulen en metadata_value_change.
    values = metadata_service.list_source_metadata_values(project.id, source.id)
    assert len(values) == 1
    assert values[0].value == "admisiones"
