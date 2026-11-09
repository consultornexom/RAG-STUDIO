"""Ronda 98 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
casos borde de la política por fuente y de la incrementalidad por
configuración en RunPipeline, con dobles en memoria. El escenario completo
de 5 fuentes / 3 tipos va en tests/integration/test_pipeline_politicas_por_fuente.py."""
from pathlib import Path

import pytest

from application.ingestion.service import IngestionService
from application.pipeline.commands.run_pipeline import RunPipeline
from application.rag.service import RagService
from domain.documents.entities import Source, SourceType
from domain.ingestion.entities import FragmentationStrategy
from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import (
    FakeTextExtractor, InMemoryChunkRepository, InMemoryExtractionRepository, InMemoryFragmentationPolicyRepository,
)
from .fakes_metadata import InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository
from .fakes_pipeline import InMemoryPipelineRunRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository

P = "p1"


@pytest.fixture
def fx(tmp_path):
    sources = InMemorySourceRepository()
    chunks = InMemoryChunkRepository()
    ingestion = IngestionService(
        sources, FakeTextExtractor(), InMemoryExtractionRepository(), InMemoryFragmentationPolicyRepository(),
        chunks, InMemoryMetadataSchemaRepository(), InMemorySourceMetadataRepository(),
    )
    rag = RagService(chunks, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
                     source_repository=sources)
    runs = InMemoryPipelineRunRepository()
    return RunPipeline(sources, ingestion, rag, runs), sources, ingestion, runs, tmp_path


def _fuente(sources, tmp_path, nombre, tipo="default", copia=True) -> Source:
    ruta = tmp_path / f"{nombre}.txt"
    ruta.write_text(f"contenido de {nombre} con varias palabras de prueba", encoding="utf-8")
    src = Source(project_id=P, title=nombre, source_type=SourceType.TXT, location=str(ruta),
                 original_copy_path=str(ruta) if copia else None, document_type_code=tipo)
    sources.save(src)
    return src


def test_tipo_sin_politica_usa_la_default_del_proyecto_y_sin_ninguna_la_interna(fx):
    run_pipeline, sources, ingestion, _, tmp = fx
    _fuente(sources, tmp, "sin_politica", "formatos")
    item = run_pipeline.execute(P).items[0]
    assert (item.policy_origin, item.policy_document_type_code) == ("interna", None)

    ingestion.set_fragmentation_policy(P, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    item = run_pipeline.execute(P).items[0]
    assert (item.policy_origin, item.policy_document_type_code, item.policy_strategy) == (
        "default_proyecto", "default", "documento_completo")
    assert item.status == PipelineItemStatus.EXITOSO and "Cambió la política" in item.reason

    ingestion.set_fragmentation_policy(P, "formatos", strategy=FragmentationStrategy.POR_TAMANIO)
    item = run_pipeline.execute(P).items[0]
    assert (item.policy_origin, item.policy_document_type_code) == ("especifica", "formatos")


def test_tipo_forzado_explicito_se_marca_como_forzado(fx):
    run_pipeline, sources, ingestion, _, tmp = fx
    ingestion.set_fragmentation_policy(P, "otro", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    _fuente(sources, tmp, "a", "programa_academico")
    run = run_pipeline.execute(P, document_type_code="otro")
    assert run.document_type_code == "otro"
    item = run.items[0]
    assert (item.policy_origin, item.policy_document_type_code, item.document_type_code) == (
        "forzada", "otro", "programa_academico")


def test_corrida_anterior_sin_huellas_se_reprocesa_una_vez_con_motivo(fx):
    run_pipeline, sources, _, runs, tmp = fx
    src = _fuente(sources, tmp, "legado")
    primera = run_pipeline.execute(P).items[0]
    # Simula una corrida guardada antes de la Ronda 98: mismo hash, sin huellas.
    runs.save(PipelineRun(project_id=P, status=PipelineRunStatus.COMPLETO, items=[PipelineRunItem(
        source_id=src.id, source_title="legado", status=PipelineItemStatus.EXITOSO,
        content_hash=primera.content_hash, steps_completed=["extraccion", "fragmentacion", "indexacion"],
    )]))
    item = run_pipeline.execute(P).items[0]
    assert item.status == PipelineItemStatus.EXITOSO
    assert "versión previa de RAG Studio" in item.reason
    assert run_pipeline.execute(P).items[0].status == PipelineItemStatus.OMITIDO


def test_si_el_ultimo_intento_fallo_no_se_omite_aunque_coincida_con_el_ultimo_exito(fx):
    run_pipeline, sources, _, runs, tmp = fx
    src = _fuente(sources, tmp, "a")
    ok = run_pipeline.execute(P).items[0]
    runs.save(PipelineRun(project_id=P, status=PipelineRunStatus.COMPLETO_CON_ERRORES, items=[PipelineRunItem(
        source_id=src.id, source_title="a", status=PipelineItemStatus.FALLIDO, content_hash=ok.content_hash,
        steps_completed=["extraccion", "fragmentacion"], error="fallo simulado al indexar",
    )]))
    item = run_pipeline.execute(P).items[0]
    assert item.status == PipelineItemStatus.EXITOSO
    assert "terminó como fallido" in item.reason


def test_el_hash_se_toma_de_la_copia_que_se_extrae_no_de_la_ruta_externa(fx):
    """Proyecto llevado a otro equipo: la ruta externa ya no existe, pero la
    copia en sources/original/ sí. Antes el hash salía None y la fuente se
    reprocesaba en todas las corridas."""
    run_pipeline, sources, _, _, tmp = fx
    copia = tmp / "copia_interna.txt"
    copia.write_text("contenido real guardado en el proyecto", encoding="utf-8")
    sources.save(Source(project_id=P, title="portada", source_type=SourceType.TXT,
                        location="/ruta/de/otro/equipo/no_existe.txt", original_copy_path=str(copia)))
    assert run_pipeline.execute(P).items[0].status == PipelineItemStatus.EXITOSO
    item = run_pipeline.execute(P).items[0]
    assert item.status == PipelineItemStatus.OMITIDO and item.content_hash


def test_sin_archivo_legible_se_intenta_procesar_con_motivo(fx):
    run_pipeline, sources, _, _, _ = fx
    sources.save(Source(project_id=P, title="perdida", source_type=SourceType.TXT,
                        location="/no/existe.txt"))
    item = run_pipeline.execute(P).items[0]
    assert item.content_hash is None
    assert item.reason.startswith("No se pudo leer el archivo")


def test_cambiar_la_ruta_externa_sin_tocar_la_copia_no_reprocesa(fx):
    run_pipeline, sources, _, _, tmp = fx
    src = _fuente(sources, tmp, "a")
    copia = tmp / "a_copia.txt"
    copia.write_text("copia interna estable", encoding="utf-8")
    sources.save(src.model_copy(update={"original_copy_path": str(copia)}))
    run_pipeline.execute(P)
    Path(src.location).write_text("el archivo externo cambió, pero se extrae de la copia", encoding="utf-8")
    assert run_pipeline.execute(P).items[0].status == PipelineItemStatus.OMITIDO
