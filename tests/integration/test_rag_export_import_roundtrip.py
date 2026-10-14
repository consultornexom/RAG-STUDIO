"""Confirma que el índice vectorial (Etapa 4) viaja dentro de
.agentproj sin cambios en el empaquetador -- mismo patrón ya probado
para Etapa 2 (fuentes/metadatos) y Etapa 3 (fragmentos): cuarta
confirmación de esta propiedad arquitectónica.

FilesystemProjectPackager recorre project_dir/** recursivamente, y
InstallationPaths.qdrant_index_dir vive dentro de project_dir/indexes/
-- por eso no hizo falta tocar el empaquetador para que el índice
vectorial también sea portable."""
from __future__ import annotations

from pathlib import Path

from application.documents.service import DocumentService
from application.ingestion.service import IngestionService
from application.projects.service import ProjectService
from application.rag.service import RagService
from domain.documents.entities import SourceType
from domain.ingestion.entities import FragmentationStrategy
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import (
    SqlAlchemyChunkRepository, SqlAlchemyExtractionRepository, SqlAlchemyFragmentationPolicyRepository,
)
from infrastructure.database.metadata_repositories import (
    SqlAlchemyMetadataSchemaRepository, SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.database.repositories import SqlAlchemyConfigurationRepository, SqlAlchemyProjectRepository
from infrastructure.extraction.text_extractors import CompositeTextExtractor
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

from ..unit.application.fakes_rag import FakeEmbeddingProvider


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
    rag_service = RagService(
        SqlAlchemyChunkRepository(paths), FakeEmbeddingProvider(dimensions=8),
        QdrantLocalVectorStore(paths), SqlAlchemyIndexInfoRepository(paths),
    )
    return project_service, document_service, ingestion_service, rag_service, paths


def test_vector_index_survives_export_import_without_packager_changes(tmp_path):
    project_service, document_service, ingestion_service, rag_service, _ = _bootstrap_services(tmp_path / "laptop_a")
    project = project_service.create_project("Agente con índice vectorial")

    source_file = tmp_path / "aviso.txt"
    source_file.write_text("Contenido del aviso que se va a fragmentar completo.", encoding="utf-8")
    source = document_service.register_source(project.id, "Aviso", SourceType.TXT, location=str(source_file))

    ingestion_service.extract_source_text(project.id, source.id)
    ingestion_service.set_fragmentation_policy(project.id, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    ingestion_service.fragment_source(project.id, source.id)
    indexed = rag_service.index_source(project.id, source.id)
    assert indexed == 1

    export_path = tmp_path / "export.agentproj"
    project_service.export_project(project.id, str(export_path))

    project_service_b, _, ingestion_service_b, rag_service_b, _ = _bootstrap_services(tmp_path / "laptop_b")
    imported = project_service_b.import_project(str(export_path), identity_policy="preserve")

    # El índice importado debe responder búsquedas sin volver a indexar nada.
    info = rag_service_b.get_index_info(imported.id)
    assert info is not None
    assert info.points_count == 1

    results = rag_service_b.search(imported.id, "aviso fragmentado", limit=5)
    assert len(results) == 1
    assert results[0].chunk.text == "Contenido del aviso que se va a fragmentar completo."

    # Los fragmentos también siguen ahí (Etapa 3, ya confirmado antes;
    # se repite aquí solo para dejar constancia de que ambos viajan juntos).
    imported_chunks = ingestion_service_b.list_chunks(imported.id, source.id)
    assert len(imported_chunks) == 1
