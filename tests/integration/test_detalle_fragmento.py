"""Ronda 99 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
detalle de solo lectura de un fragmento y contexto jerárquico derivado,
sobre un AppContext real (SQLite real, extractor real, Qdrant local real;
embeddings determinísticos para no depender de red)."""
from __future__ import annotations

import pytest

from application.pipeline.commands.run_pipeline import RunPipeline
from application.rag.service import RagService
from domain.documents.entities import SourceType
from domain.ingestion.entities import ChunkType, FragmentationStrategy
from domain.pipeline.entities import PipelineItemStatus
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.pipeline_repositories import SqlAlchemyPipelineRunRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

from ..unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

TORRES_LANDA = """# Bachillerato — Plantel Torres Landa

## Plan de estudios

### 4to. semestre
* Matemáticas IV
* Mercadotecnia

## Área Económico-Administrativa y Humanidades

### 5.º semestre
* Geografía
* Economía I
* Matemáticas Financieras I
* Derecho I

### 6.º semestre
* Filosofía
* Economía II

## Área Físico-Matemática y Químico-Biológicas

### 5.º semestre
* Geografía
* Temas Selectos de Química I
* Cálculo diferencial

### 6.º semestre
* Filosofía
* Cálculo Integral
"""


@pytest.fixture
def fx(app_context, tmp_path):
    ctx = app_context
    pid = ctx.project_service.create_project("AGENTE UDL - LOTE01_Bachillerato").id
    meta = ctx.metadata_service
    sid = meta.create_schema(pid).id
    cat = meta.create_catalog(pid, "campus_udl")
    meta.add_catalog_entry(pid, cat.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(pid, cat.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(pid, sid, "campus", "Campus o plantel", "seleccion_multiple", multiple=True,
                              filterable=True, inherited_by_chunks=True, catalog_id=cat.id)
    meta.add_field_definition(pid, sid, "programa", "Programa", "texto", inherited_by_chunks=True)
    ctx.ingestion_service.set_fragmentation_policy(pid, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO)
    ruta = tmp_path / "bachillerato_torres_landa.md"
    ruta.write_text(TORRES_LANDA, encoding="utf-8")
    src = ctx.document_service.register_source(pid, "bachillerato_torres_landa.md", SourceType.MARKDOWN,
                                               location=str(ruta), document_type_code="programa_academico").id
    meta.set_source_metadata_value(pid, sid, src, "campus", ["hilario_medina", "torres_landa"])
    meta.set_source_metadata_value(pid, sid, src, "programa", "Bachillerato")
    paths = ctx.paths
    rag = RagService(SqlAlchemyChunkRepository(paths), WordOverlapFakeEmbeddingProvider(), QdrantLocalVectorStore(paths),
                     SqlAlchemyIndexInfoRepository(paths), source_repository=SqlAlchemySourceRepository(paths))
    runs = SqlAlchemyPipelineRunRepository(paths)
    pipeline = RunPipeline(SqlAlchemySourceRepository(paths), ctx.ingestion_service, rag, runs)
    run = pipeline.execute(pid, schema_id=sid)
    assert run.items[0].status == PipelineItemStatus.EXITOSO
    return ctx, pid, sid, src, pipeline, rag


def _chunks(ctx, pid, src):
    return ctx.ingestion_service.list_chunks(pid, src)


def _quinto(ctx, pid, src):
    return [c for c in _chunks(ctx, pid, src) if c.section_title == "5.º semestre"]


def test_detalle_muestra_el_texto_integro_y_exacto(fx):
    ctx, pid, _, src, _, _ = fx
    for chunk in _chunks(ctx, pid, src):
        detail = ctx.ingestion_service.get_chunk_detail(pid, src, chunk.id)
        assert detail.chunk.text == chunk.text  # mismo contenido almacenado, sin transformar
        assert detail.chunk.model_dump() == chunk.model_dump()
    economico, _fisico = _quinto(ctx, pid, src)
    texto = ctx.ingestion_service.get_chunk_detail(pid, src, economico.id).chunk.text
    assert texto.splitlines() == ["### 5.º semestre", "* Geografía", "* Economía I", "* Matemáticas Financieras I",
                                  "* Derecho I"]


def test_propiedades_relaciones_y_fuente(fx):
    ctx, pid, _, src, _, _ = fx
    economico, _ = _quinto(ctx, pid, src)
    d = ctx.ingestion_service.get_chunk_detail(pid, src, economico.id)
    assert (d.source_title, d.source_position, d.source_count) == ("bachillerato_torres_landa.md", 1, 1)
    assert d.source_document_type_code == "programa_academico"
    assert d.chunk.chunk_type == ChunkType.TEXTO and d.chunk.section_title == "5.º semestre"
    assert d.previous.section_title == "Área Económico-Administrativa y Humanidades"
    assert d.next.section_title == "6.º semestre"
    assert d.previous.found and d.next.found
    assert d.parent is None  # la sección cupo en un solo fragmento
    assert d.indexable
    area = ctx.ingestion_service.get_chunk_detail(pid, src, d.previous.id)
    assert not area.indexable and "Solo contiene su encabezado" in area.indexable_reason


def test_metadatos_heredados_con_valor_multiple(fx):
    ctx, pid, _, src, _, _ = fx
    d = ctx.ingestion_service.get_chunk_detail(pid, src, _quinto(ctx, pid, src)[0].id)
    por_campo = {m.field_id: m for m in d.inherited_metadata}
    campus = por_campo["campus"]
    assert campus.multiple and campus.display_name == "Campus o plantel"
    assert campus.values == ["hilario_medina", "torres_landa"]
    assert campus.raw_value == "hilario_medina|torres_landa"
    assert (por_campo["programa"].values, por_campo["programa"].multiple) == (["Bachillerato"], False)


def test_contexto_jerarquico_distingue_los_dos_quinto_semestre(fx):
    """Fragmentos 5.º semestre de áreas distintas: misma sección, distinta ruta."""
    ctx, pid, _, src, _, _ = fx
    economico, fisico = (ctx.ingestion_service.get_chunk_detail(pid, src, c.id) for c in _quinto(ctx, pid, src))
    assert economico.heading_context_status == fisico.heading_context_status == "derivado"
    assert economico.heading_path == [
        "Bachillerato — Plantel Torres Landa", "Área Económico-Administrativa y Humanidades", "5.º semestre"]
    assert fisico.heading_path == [
        "Bachillerato — Plantel Torres Landa", "Área Físico-Matemática y Químico-Biológicas", "5.º semestre"]
    assert economico.heading_path_levels == [1, 2, 3]
    # Pérdida de contexto confirmada: el texto indexado no lleva ni el área ni el plantel.
    assert economico.heading_context_missing == [
        "Bachillerato — Plantel Torres Landa", "Área Económico-Administrativa y Humanidades"]


def test_ver_detalle_no_modifica_nada_ni_reindexa(fx):
    ctx, pid, sid, src, pipeline, rag = fx
    antes = [c.model_dump() for c in _chunks(ctx, pid, src)]
    info_antes = rag.get_index_info(pid) if hasattr(rag, "get_index_info") else None
    for chunk in _chunks(ctx, pid, src):
        ctx.ingestion_service.get_chunk_detail(pid, src, chunk.id)
    assert [c.model_dump() for c in _chunks(ctx, pid, src)] == antes
    if info_antes is not None:
        assert rag.get_index_info(pid) == info_antes
    # La incrementalidad de la Ronda 98 no ve ningún cambio: la fuente se omite.
    assert pipeline.execute(pid, schema_id=sid).items[0].status == PipelineItemStatus.OMITIDO


def test_fragmento_inexistente_devuelve_none(fx):
    ctx, pid, _, src, _, _ = fx
    assert ctx.ingestion_service.get_chunk_detail(pid, src, "no-existe") is None


def test_relacion_padre_hijo_y_texto_con_caracteres_especiales(app_context, tmp_path):
    ctx = app_context
    pid = ctx.project_service.create_project("Padre e hijos").id
    ctx.ingestion_service.set_fragmentation_policy(pid, "default", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                                   target_tokens=12, overlap_tokens=0, min_tokens=1)
    cuerpo = " ".join(f"palabra{i}" for i in range(40))
    texto = f"# Sección larga\n{cuerpo}\nLínea con <b>etiquetas</b> & símbolos: ñ, ü, «», 5.º, \\t y $PATH\n"
    ruta = tmp_path / "larga.md"
    ruta.write_text(texto, encoding="utf-8")
    src = ctx.document_service.register_source(pid, "larga.md", SourceType.MARKDOWN, location=str(ruta)).id
    ctx.ingestion_service.extract_source_text(pid, src)
    chunks = ctx.ingestion_service.fragment_source(pid, src)
    padre = next(c for c in chunks if c.chunk_type == ChunkType.PADRE)
    hijo = next(c for c in chunks if c.parent_chunk_id == padre.id)
    d = ctx.ingestion_service.get_chunk_detail(pid, src, hijo.id)
    assert d.parent.found and d.parent.id == padre.id and d.parent.chunk_index == padre.chunk_index
    dp = ctx.ingestion_service.get_chunk_detail(pid, src, padre.id)
    assert not dp.indexable and "PADRE" in dp.indexable_reason
    assert "<b>etiquetas</b> & símbolos: ñ, ü, «», 5.º, \\t y $PATH" in dp.chunk.text
    assert dp.heading_path == ["Sección larga"]
