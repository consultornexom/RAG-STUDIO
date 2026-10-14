"""Prueba de punta a punta del contexto RAG sobre un AppContext real
(bootstrap completo, SQLite real, Qdrant local real) -- mismo patrón
que test_ingestion_end_to_end.py, pero para la Etapa 4.

Se construye un RagService alterno que reutiliza los repositorios
reales del AppContext (mismo project.db, mismo directorio Qdrant) pero
con un EmbeddingProvider determinístico en vez del FastEmbed real de
app_context.rag_service -- así la prueba no depende de red hacia
Hugging Face, sin dejar de ejercitar el ChunkRepository y el
VectorStore de producción de verdad."""
from __future__ import annotations

from application.rag.service import RagService
from domain.documents.entities import SourceType
from domain.ingestion.entities import FragmentationStrategy
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

from ..unit.application.fakes_rag import FakeEmbeddingProvider


def _make_deterministic_rag_service(app_context) -> RagService:
    return RagService(
        SqlAlchemyChunkRepository(app_context.paths),
        FakeEmbeddingProvider(dimensions=8),
        QdrantLocalVectorStore(app_context.paths),
        SqlAlchemyIndexInfoRepository(app_context.paths),
    )


def test_index_and_search_over_real_app_context(app_context, tmp_path):
    source_path = tmp_path / "reglamento.md"
    source_path.write_text(
        "# Admisión\nRequisitos de admisión para el ciclo escolar, incluye boleta.\n\n"
        "# Bajas\nProceso para tramitar una baja temporal del alumno.\n",
        encoding="utf-8",
    )

    project = app_context.project_service.create_project("Piloto RAG")
    source = app_context.document_service.register_source(
        project.id, "Reglamento", SourceType.MARKDOWN, location=str(source_path),
    )
    app_context.ingestion_service.extract_source_text(project.id, source.id)
    app_context.ingestion_service.set_fragmentation_policy(
        project.id, "reglamento", strategy=FragmentationStrategy.POR_ENCABEZADO,
    )
    app_context.ingestion_service.fragment_source(project.id, source.id, document_type_code="reglamento")

    rag = _make_deterministic_rag_service(app_context)
    n = rag.index_source(project.id, source.id)
    assert n == 2

    results = rag.search(project.id, "boleta de admisión", limit=5)
    assert len(results) == 2
    assert {r.chunk.section_title for r in results} == {"Admisión", "Bajas"}

    info = rag.get_index_info(project.id)
    assert info is not None
    assert info.points_count == 2


def test_reindexing_after_refragmenting_does_not_duplicate_points(app_context, tmp_path):
    source_path = tmp_path / "aviso.txt"
    source_path.write_text("Contenido del aviso que se va a fragmentar completo.", encoding="utf-8")

    project = app_context.project_service.create_project("Piloto RAG 2")
    source = app_context.document_service.register_source(
        project.id, "Aviso", SourceType.TXT, location=str(source_path),
    )
    app_context.ingestion_service.extract_source_text(project.id, source.id)
    app_context.ingestion_service.set_fragmentation_policy(
        project.id, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO,
    )
    app_context.ingestion_service.fragment_source(project.id, source.id)

    rag = _make_deterministic_rag_service(app_context)
    rag.index_source(project.id, source.id)

    # Volver a fragmentar genera Chunk con ids nuevos (Etapa 3: los
    # ids no son estables entre corridas) -- reindexar debe seguir
    # dejando exactamente un punto por fragmento, no acumular.
    app_context.ingestion_service.fragment_source(project.id, source.id)
    rag.index_source(project.id, source.id)

    assert rag.get_index_info(project.id).points_count == 1
