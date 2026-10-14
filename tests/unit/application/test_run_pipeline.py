"""Pruebas unitarias de RunPipeline (Etapa 3: pipeline reproducible)
con dobles de prueba en memoria -- salvo el archivo real en disco que
necesita _hash_file para la incrementalidad, sin red ni Qdrant real."""
import pytest

from application.ingestion.service import IngestionService
from application.pipeline.commands.run_pipeline import RunPipeline
from application.rag.service import RagService
from domain.documents.entities import SourceType
from domain.pipeline.entities import PipelineItemStatus, PipelineRunStatus

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import FakeTextExtractor, InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository
from .fakes_metadata import InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository
from .fakes_pipeline import InMemoryPipelineRunRepository
from .fakes_rag import (
    FakeEmbeddingProvider, FakeImageEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository,
)


@pytest.fixture
def pipeline(tmp_path):
    source_repository = InMemorySourceRepository()
    schema_repository = InMemoryMetadataSchemaRepository()
    source_metadata_repository = InMemorySourceMetadataRepository()
    extraction_repository = InMemoryExtractionRepository()
    chunk_repository = InMemoryChunkRepository()

    ingestion_service = IngestionService(
        source_repository, FakeTextExtractor(), extraction_repository, InMemoryFragmentationPolicyRepository(),
        chunk_repository, schema_repository, source_metadata_repository,
    )
    rag_service = RagService(
        chunk_repository, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repository,
    )
    run_repository = InMemoryPipelineRunRepository()
    run_pipeline = RunPipeline(source_repository, ingestion_service, rag_service, run_repository)
    return run_pipeline, source_repository, run_repository, tmp_path


def _register(source_repository, tmp_path, title: str, filename: str, content: str):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    from domain.documents.entities import Source
    source = Source(project_id="p1", title=title, source_type=SourceType.TXT, location=str(path))
    source_repository.save(source)
    return source


def test_run_pipeline_processes_all_sources_successfully(pipeline):
    run_pipeline, source_repository, _, tmp_path = pipeline
    _register(source_repository, tmp_path, "Uno", "uno.txt", "contenido real de la fuente uno con palabras suficientes")
    _register(source_repository, tmp_path, "Dos", "dos.txt", "contenido real de la fuente dos con palabras suficientes")

    run = run_pipeline.execute("p1")

    assert run.status == PipelineRunStatus.COMPLETO
    assert len(run.items) == 2
    assert all(item.status == PipelineItemStatus.EXITOSO for item in run.items)
    assert all(item.steps_completed == ["extraccion", "fragmentacion", "indexacion"] for item in run.items)
    assert all(item.chunks_indexed > 0 for item in run.items)


def test_run_pipeline_skips_unchanged_source_on_second_run(pipeline):
    run_pipeline, source_repository, _, tmp_path = pipeline
    _register(source_repository, tmp_path, "Uno", "uno.txt", "contenido estable que no cambia entre corridas")

    first = run_pipeline.execute("p1")
    second = run_pipeline.execute("p1")

    assert first.items[0].status == PipelineItemStatus.EXITOSO
    assert second.items[0].status == PipelineItemStatus.OMITIDO
    assert second.items[0].content_hash == first.items[0].content_hash
    assert second.status == PipelineRunStatus.COMPLETO


def test_run_pipeline_reprocesses_source_after_file_changes(pipeline):
    run_pipeline, source_repository, _, tmp_path = pipeline
    source = _register(source_repository, tmp_path, "Uno", "uno.txt", "versión original del archivo")

    run_pipeline.execute("p1")
    # El archivo cambia de verdad en disco -- no solo Source.updated_at,
    # que ExtractSourceText/RunPipeline no usan como señal.
    from pathlib import Path
    Path(source.location).write_text("versión modificada del archivo, distinta de la anterior", encoding="utf-8")

    second = run_pipeline.execute("p1")
    assert second.items[0].status == PipelineItemStatus.EXITOSO


def test_run_pipeline_marks_one_failed_source_without_aborting_the_rest(pipeline):
    run_pipeline, source_repository, _, tmp_path = pipeline
    good = _register(source_repository, tmp_path, "Buena", "buena.txt", "contenido real y utilizable de la fuente")
    bad_path = tmp_path / "vacia.txt"
    bad_path.write_text("no importa, el extractor de prueba la reporta vacía", encoding="utf-8")
    from domain.documents.entities import Source
    bad = Source(project_id="p1", title="Vacía", source_type=SourceType.TXT, location=str(bad_path))
    source_repository.save(bad)

    # FakeTextExtractor "enlatado" por ubicación: simula una extracción
    # real que falla (texto vacío) para una sola fuente, sin tocar el
    # sistema de archivos -- misma técnica que test_ingestion_service.py.
    run_pipeline._ingestion._extract._extractor = FakeTextExtractor(
        canned={bad.location: ("   ", "fake", [], [])},
    )

    run = run_pipeline.execute("p1")

    by_id = {item.source_id: item for item in run.items}
    assert by_id[good.id].status == PipelineItemStatus.EXITOSO
    assert by_id[bad.id].status == PipelineItemStatus.FALLIDO
    assert "no produjo texto utilizable" in by_id[bad.id].error
    assert run.status == PipelineRunStatus.COMPLETO_CON_ERRORES
    assert run.has_critical_errors is True
    assert run.is_usable_as_index_base is False


def test_run_pipeline_stops_early_when_cancelled_between_sources(pipeline):
    # is_cancelled se revisa tanto entre fuentes (bucle externo de
    # RunPipeline.execute) como dentro de cada una (extract_source_text/
    # fragment_source también lo reciben) -- para cancelar justo
    # *después* de terminar la primera fuente y *antes* de empezar la
    # segunda (sin depender de contar cuántas veces se invoca por
    # dentro, que varía con el contenido), se envuelve _process_source
    # para saber cuántas fuentes ya se terminaron de procesar.
    run_pipeline, source_repository, _, tmp_path = pipeline
    _register(source_repository, tmp_path, "Uno", "uno.txt", "contenido de la primera fuente para procesar")
    _register(source_repository, tmp_path, "Dos", "dos.txt", "contenido de la segunda fuente para procesar")

    original_process_source = run_pipeline._process_source
    processed: list = []

    def _wrapped(*args, **kwargs):
        result = original_process_source(*args, **kwargs)
        processed.append(result)
        return result

    run_pipeline._process_source = _wrapped

    def is_cancelled():
        return len(processed) >= 1

    run = run_pipeline.execute("p1", is_cancelled=is_cancelled)

    assert run.status == PipelineRunStatus.CANCELADO
    assert len(run.items) == 1
    assert run.items[0].status == PipelineItemStatus.EXITOSO


def test_run_pipeline_on_project_without_sources_completes_with_no_items(pipeline):
    run_pipeline, _, _, _ = pipeline
    run = run_pipeline.execute("p1")
    assert run.status == PipelineRunStatus.COMPLETO
    assert run.items == []


def test_run_pipeline_saves_the_run_via_the_repository(pipeline):
    run_pipeline, source_repository, run_repository, tmp_path = pipeline
    _register(source_repository, tmp_path, "Uno", "uno.txt", "contenido cualquiera de prueba")

    run = run_pipeline.execute("p1")

    saved = run_repository.get("p1", run.id)
    assert saved is not None
    assert saved.status == run.status
    assert len(saved.items) == len(run.items)


# ---------- SourceType.IMAGEN_NATIVA (cierre del vacío documentado en la Ronda 66, punto 226) ----------

@pytest.fixture
def pipeline_with_images(tmp_path):
    """Mismo fixture que `pipeline`, pero con un
    image_embedding_provider real (FakeImageEmbeddingProvider) -- sin
    él, RagService.index_image_source lanzaría
    ImageSearchUnavailableError (capacidad opcional, ver Ronda 66)."""
    source_repository = InMemorySourceRepository()
    schema_repository = InMemoryMetadataSchemaRepository()
    source_metadata_repository = InMemorySourceMetadataRepository()
    extraction_repository = InMemoryExtractionRepository()
    chunk_repository = InMemoryChunkRepository()

    # ImageNativeExtractor real siempre devuelve texto vacío -- se
    # imita aquí con FakeTextExtractor "enlatado" para esa ubicación,
    # habilitando además SourceType.IMAGEN_NATIVA en supported_types
    # (fuera de la lista por defecto de este doble).
    ingestion_service = IngestionService(
        source_repository,
        FakeTextExtractor(supported_types={SourceType.TXT, SourceType.IMAGEN_NATIVA}),
        extraction_repository, InMemoryFragmentationPolicyRepository(),
        chunk_repository, schema_repository, source_metadata_repository,
    )
    rag_service = RagService(
        chunk_repository, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repository, image_embedding_provider=FakeImageEmbeddingProvider(),
    )
    run_repository = InMemoryPipelineRunRepository()
    run_pipeline = RunPipeline(source_repository, ingestion_service, rag_service, run_repository)
    return run_pipeline, source_repository, chunk_repository, tmp_path


def _register_image(source_repository, tmp_path, title: str, filename: str):
    from domain.documents.entities import Source
    path = tmp_path / filename
    path.write_bytes(b"contenido binario cualquiera, no importa para esta prueba")
    source = Source(
        project_id="p1", title=title, source_type=SourceType.IMAGEN_NATIVA,
        location=str(path), original_copy_path=str(path),
    )
    source_repository.save(source)
    return source


def test_run_pipeline_indexes_an_image_native_source_via_index_image_source(pipeline_with_images):
    run_pipeline, source_repository, chunk_repository, tmp_path = pipeline_with_images
    image = _register_image(source_repository, tmp_path, "Logo", "logo.png")

    run = run_pipeline.execute("p1")

    assert run.status == PipelineRunStatus.COMPLETO
    [item] = run.items
    assert item.status == PipelineItemStatus.EXITOSO
    assert item.steps_completed == ["extraccion", "fragmentacion", "indexacion"]
    # Antes de este cambio, index_source (el de texto) indexaba 0
    # fragmentos en silencio para una imagen nativa -- ahora
    # RunPipeline llama a index_image_source, que sí produce el único
    # Chunk tipo IMAGEN de la fuente.
    assert item.chunks_indexed == 1
    [chunk] = chunk_repository.list_for_source("p1", image.id)
    assert chunk.chunk_type.value == "imagen"


def test_run_pipeline_processes_a_mix_of_text_and_image_sources_independently(pipeline_with_images):
    run_pipeline, source_repository, chunk_repository, tmp_path = pipeline_with_images
    text_path = tmp_path / "texto.txt"
    text_path.write_text("contenido real de una fuente de texto con palabras suficientes", encoding="utf-8")
    from domain.documents.entities import Source
    text_source = Source(project_id="p1", title="Texto", source_type=SourceType.TXT, location=str(text_path))
    source_repository.save(text_source)
    image = _register_image(source_repository, tmp_path, "Logo", "logo.png")

    run = run_pipeline.execute("p1")

    assert run.status == PipelineRunStatus.COMPLETO
    by_id = {item.source_id: item for item in run.items}
    assert by_id[text_source.id].status == PipelineItemStatus.EXITOSO
    assert by_id[text_source.id].chunks_indexed > 0
    assert by_id[image.id].status == PipelineItemStatus.EXITOSO
    assert by_id[image.id].chunks_indexed == 1
    assert chunk_repository.list_for_source("p1", text_source.id)[0].chunk_type.value == "texto"
    assert chunk_repository.list_for_source("p1", image.id)[0].chunk_type.value == "imagen"
