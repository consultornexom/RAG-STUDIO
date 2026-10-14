"""Pruebas unitarias de PipelineService (fachada de application para el
contexto Pipeline)."""
from application.ingestion.service import IngestionService
from application.pipeline.service import PipelineService
from application.rag.service import RagService
from domain.documents.entities import Source, SourceType
from domain.pipeline.entities import PipelineItemStatus, PipelineRunStatus

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import FakeTextExtractor, InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository
from .fakes_metadata import InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository
from .fakes_pipeline import InMemoryPipelineRunRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository


def _make_service(tmp_path):
    source_repository = InMemorySourceRepository()
    chunk_repository = InMemoryChunkRepository()
    ingestion_service = IngestionService(
        source_repository, FakeTextExtractor(), InMemoryExtractionRepository(),
        InMemoryFragmentationPolicyRepository(), chunk_repository,
        InMemoryMetadataSchemaRepository(), InMemorySourceMetadataRepository(),
    )
    rag_service = RagService(
        chunk_repository, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repository,
    )
    run_repository = InMemoryPipelineRunRepository()
    service = PipelineService(source_repository, ingestion_service, rag_service, run_repository)

    path = tmp_path / "fuente.txt"
    path.write_text("contenido real de prueba con palabras suficientes", encoding="utf-8")
    source_repository.save(Source(project_id="p1", title="Fuente", source_type=SourceType.TXT, location=str(path)))
    return service


def test_run_processes_the_project_and_returns_a_completed_run(tmp_path):
    service = _make_service(tmp_path)
    run = service.run("p1")
    assert run.status == PipelineRunStatus.COMPLETO
    assert len(run.items) == 1
    assert run.items[0].status == PipelineItemStatus.EXITOSO


def test_get_run_and_list_runs_reflect_what_was_saved(tmp_path):
    service = _make_service(tmp_path)
    run = service.run("p1")

    assert service.get_run("p1", run.id).id == run.id
    assert [r.id for r in service.list_runs("p1")] == [run.id]


def test_get_run_returns_none_for_unknown_run(tmp_path):
    service = _make_service(tmp_path)
    assert service.get_run("p1", "no-existe") is None
