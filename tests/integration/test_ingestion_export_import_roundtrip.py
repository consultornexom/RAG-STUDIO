"""Confirma que las tablas de Ingesta (Etapa 3) viajan dentro de
.agentproj sin cambios en el empaquetador — mismo patrón ya probado
para Etapa 2 (fuentes/metadatos)."""
from __future__ import annotations

from pathlib import Path

from application.documents.service import DocumentService
from application.ingestion.service import IngestionService
from application.projects.service import ProjectService
from domain.documents.entities import SourceType
from domain.ingestion.entities import FragmentationStrategy
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import (
    SqlAlchemyChunkRepository, SqlAlchemyExtractionRepository, SqlAlchemyFragmentationPolicyRepository,
)
from infrastructure.database.metadata_repositories import (
    SqlAlchemyMetadataSchemaRepository, SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.repositories import SqlAlchemyConfigurationRepository, SqlAlchemyProjectRepository
from infrastructure.extraction.text_extractors import CompositeTextExtractor
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths


def _bootstrap_services(base_dir: Path):
    paths = InstallationPaths(base_dir)
    paths.ensure_installation_layout()

    project_service = ProjectService(
        SqlAlchemyProjectRepository(paths), SqlAlchemyConfigurationRepository(paths),
        FilesystemProjectPackager(paths),
    )
    source_repository = SqlAlchemySourceRepository(paths)
    document_service = DocumentService(source_repository, SqlAlchemyExtractionRepository(paths))
    schema_repository = SqlAlchemyMetadataSchemaRepository(paths)
    source_metadata_repository = SqlAlchemySourceMetadataRepository(paths)
    ingestion_service = IngestionService(
        source_repository, CompositeTextExtractor(), SqlAlchemyExtractionRepository(paths),
        SqlAlchemyFragmentationPolicyRepository(paths), SqlAlchemyChunkRepository(paths),
        schema_repository, source_metadata_repository,
    )
    return project_service, document_service, ingestion_service, paths


def test_chunks_survive_export_import_without_packager_changes(tmp_path):
    project_service, document_service, ingestion_service, _ = _bootstrap_services(tmp_path / "laptop_a")
    project = project_service.create_project("Agente con fragmentos")

    source_file = tmp_path / "aviso.txt"
    source_file.write_text("Contenido del aviso que se va a fragmentar completo.", encoding="utf-8")
    source = document_service.register_source(project.id, "Aviso", SourceType.TXT, location=str(source_file))

    ingestion_service.extract_source_text(project.id, source.id)
    ingestion_service.set_fragmentation_policy(project.id, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    original_chunks = ingestion_service.fragment_source(project.id, source.id)
    assert len(original_chunks) == 1

    export_path = tmp_path / "export.agentproj"
    project_service.export_project(project.id, str(export_path))

    project_service_b, document_service_b, ingestion_service_b, _ = _bootstrap_services(tmp_path / "laptop_b")
    imported = project_service_b.import_project(str(export_path), identity_policy="preserve")

    imported_chunks = ingestion_service_b.list_chunks(imported.id, source.id)
    assert len(imported_chunks) == 1
    assert imported_chunks[0].text == original_chunks[0].text

    imported_record = ingestion_service_b.get_extraction_record(imported.id, source.id)
    assert imported_record is not None
    assert imported_record.text == "Contenido del aviso que se va a fragmentar completo."

    imported_policies = ingestion_service_b.list_fragmentation_policies(imported.id)
    assert {p.document_type_code for p in imported_policies} == {"default"}
