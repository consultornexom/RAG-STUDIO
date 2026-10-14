"""Pruebas unitarias de RagService (IndexSource + SemanticSearch) con
dobles de prueba en memoria -- sin red, sin Qdrant real, sin fastembed
real."""
from datetime import date, timedelta

import pytest

from application.rag.queries.semantic_search import SemanticSearchResult
from application.rag.service import RagService
from domain.documents.entities import AccessLevel, Source, SourceType, SourceValidationStatus
from domain.documents.exceptions import SourceNotFoundError
from domain.ingestion.entities import Chunk, ChunkType
from domain.rag.entities import DEFAULT_COLLECTION_NAME, IMAGE_COLLECTION_NAME
from domain.rag.exceptions import (
    EmbeddingDimensionMismatchError, EmbeddingProfileComparisonUnavailableError, ImageSearchUnavailableError,
    NotAnImageSourceError, RerankerUnavailableError, SourceFilterUnavailableError,
)
from domain.rag.structured_query import StructuredAggregation, StructuredFilter

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryChunkRepository
from .fakes_rag import (
    FakeEmbeddingProvider, FakeImageEmbeddingProvider, FakeReranker, FakeVectorStore, InMemoryIndexInfoRepository,
)


def _make_service(embedder=None):
    chunk_repo = InMemoryChunkRepository()
    embedder = embedder or FakeEmbeddingProvider()
    store = FakeVectorStore()
    index_info_repo = InMemoryIndexInfoRepository()
    service = RagService(chunk_repo, embedder, store, index_info_repo)
    return service, chunk_repo, store, index_info_repo


def test_embedding_provider_embed_query_default_delegates_to_embed_texts():
    """Contrato de domain.rag.ports.EmbeddingProvider.embed_query: sin
    sobreescribirlo (caso de FakeEmbeddingProvider, igual que el modelo
    simétrico por defecto de fastembed_provider), debe dar exactamente
    el mismo vector que embed_texts([text])[0] -- ver bitácora
    2026-07-26 sobre el experimento de modelo asimétrico."""
    embedder = FakeEmbeddingProvider()
    assert embedder.embed_query("una consulta") == embedder.embed_texts(["una consulta"])[0]


def test_index_source_with_no_chunks_returns_zero_without_error():
    service, _, _, index_info_repo = _make_service()
    n = service.index_source("p1", "s-sin-fragmentos")
    assert n == 0
    assert index_info_repo.get("p1") is None  # nunca se creó índice: no había nada que indexar


def test_index_source_embeds_and_upserts_all_chunks():
    service, chunk_repo, store, index_info_repo = _make_service()
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6),
        Chunk(project_id="p1", source_id="s1", chunk_index=1, text="el perro corre en el parque", token_count=6),
    ]
    chunk_repo.save_many("p1", chunks)

    n = service.index_source("p1", "s1")
    assert n == 2
    assert store.count("p1") == 2

    info = index_info_repo.get("p1")
    assert info is not None
    assert info.embedding_provider == "fake"
    assert info.points_count == 2


def test_index_source_payload_includes_traceability_and_inherited_metadata():
    service, chunk_repo, store, _ = _make_service()
    chunk = Chunk(
        project_id="p1", source_id="s1", chunk_index=3, text="texto con metadatos", token_count=3,
        section_title="Sección X", page_start=2, page_end=3,
        inherited_metadata={"plantel": "centro"},
    )
    chunk_repo.save_many("p1", [chunk])
    service.index_source("p1", "s1")

    [point] = store._points["p1"][DEFAULT_COLLECTION_NAME].values()
    assert point.payload["source_id"] == "s1"
    assert point.payload["chunk_index"] == 3
    assert point.payload["section_title"] == "Sección X"
    assert point.payload["page_start"] == 2
    assert point.payload["page_end"] == 3
    assert point.payload["meta__plantel"] == "centro"


def test_reindexing_same_source_is_idempotent():
    service, chunk_repo, store, index_info_repo = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="texto original", token_count=2),
    ])
    service.index_source("p1", "s1")
    service.index_source("p1", "s1")
    assert store.count("p1") == 1
    assert index_info_repo.get("p1").points_count == 1


def test_indexing_two_sources_and_deleting_one_does_not_touch_the_other():
    service, chunk_repo, store, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="fuente uno", token_count=2),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="fuente dos", token_count=2),
    ])
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")
    assert store.count("p1") == 2

    # Fuente 1 ya no tiene fragmentos (se "des-fragmentó"); reindexarla
    # debe limpiar sus vectores sin tocar los de la fuente 2.
    chunk_repo.delete_for_source("p1", "s1")
    service.index_source("p1", "s1")
    assert store.count("p1") == 1


def test_search_returns_full_chunk_ordered_by_similarity():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6),
        Chunk(project_id="p1", source_id="s1", chunk_index=1, text="el perro corre en el parque", token_count=6),
    ])
    service.index_source("p1", "s1")

    results = service.search("p1", "el gato duerme en la casa", limit=5)
    assert len(results) == 2
    assert results[0].chunk.text == "el gato duerme en la casa"
    assert results[0].score >= results[1].score


def test_search_can_filter_by_source_id():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="contenido de la fuente uno", token_count=4),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="contenido de la fuente dos", token_count=4),
    ])
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")

    results = service.search("p1", "contenido", limit=10, source_id="s2")
    assert len(results) == 1
    assert results[0].chunk.source_id == "s2"


def test_search_on_empty_project_returns_empty_list():
    service, _, _, _ = _make_service()
    assert service.search("p1", "cualquier cosa", limit=5) == []


def test_search_rejects_blank_query():
    service, _, _, _ = _make_service()
    with pytest.raises(ValueError):
        service.search("p1", "   ", limit=5)


def test_index_source_skips_heading_only_chunks_without_body():
    service, chunk_repo, store, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="s1", chunk_index=0, text="### Plan de Estudios",
            token_count=3, section_title="Plan de Estudios",
        ),
        Chunk(
            project_id="p1", source_id="s1", chunk_index=1,
            text="#### 1er. Cuatrimestre\nÁlgebra\nCálculo", token_count=6,
            section_title="1er. Cuatrimestre",
        ),
    ])
    n = service.index_source("p1", "s1")
    assert n == 1  # el encabezado sin cuerpo no se indexa
    assert store.count("p1") == 1
    [point] = store._points["p1"][DEFAULT_COLLECTION_NAME].values()
    assert point.payload["section_title"] == "1er. Cuatrimestre"


def test_index_source_keeps_short_single_line_chunks_without_section_title():
    # Un fragmento corto de una sola línea SIN section_title (p. ej.
    # POR_TAMANIO o DOCUMENTO_COMPLETO) nunca debe descartarse: solo
    # los fragmentos con encabezado pueden ser "solo el título".
    service, chunk_repo, store, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="Aviso corto sin encabezado", token_count=4),
    ])
    n = service.index_source("p1", "s1")
    assert n == 1
    assert store.count("p1") == 1


def test_index_source_returns_zero_when_all_chunks_are_heading_only():
    service, chunk_repo, store, index_info_repo = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="s1", chunk_index=0, text="## Solo título",
            token_count=2, section_title="Solo título",
        ),
    ])
    n = service.index_source("p1", "s1")
    assert n == 0
    assert store.count("p1") == 0
    assert index_info_repo.get("p1") is None


def test_index_source_never_sends_padre_chunks_to_the_vector_store():
    # Pista B.1 del ADR-003 (docs proyecto/
    # RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx, sección 7,
    # riesgo explícitamente señalado): un chunk PADRE es un Chunk real
    # en el repositorio -- se recupera por id para expandir contexto
    # -- pero jamás debe llegar al embedding provider ni al
    # VectorStore, así compita o no con sus hijos por section_title.
    service, chunk_repo, store, _ = _make_service()
    padre = Chunk(
        project_id="p1", source_id="s1", chunk_index=2, text="Sección completa con todo su contenido",
        token_count=6, section_title="Sección B", chunk_type=ChunkType.PADRE,
    )
    hijo_1 = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="primera mitad de la sección",
        token_count=5, section_title="Sección B", parent_chunk_id=padre.id,
    )
    hijo_2 = Chunk(
        project_id="p1", source_id="s1", chunk_index=1, text="segunda mitad de la sección",
        token_count=5, section_title="Sección B", parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [hijo_1, hijo_2, padre])

    n = service.index_source("p1", "s1")
    assert n == 2  # solo los dos hijos, nunca el padre
    assert store.count("p1") == 2
    indexed_ids = {point.id for point in store._points["p1"][DEFAULT_COLLECTION_NAME].values()}
    assert padre.id not in indexed_ids
    assert {hijo_1.id, hijo_2.id} == indexed_ids


def test_index_source_does_index_estructurado_chunks_unlike_padre():
    # Pista B.2 del ADR-003: a diferencia de PADRE, un chunk
    # ESTRUCTURADO SÍ es contenido narrativo legítimo (la tabla
    # Markdown de siempre) -- debe llegar al VectorStore igual que un
    # chunk TEXTO. El filtro existente en IndexSource (excluir PADRE +
    # heading-only) ya deja pasar ESTRUCTURADO sin ningún cambio de
    # código -- esta prueba fija esa garantía para no perderla en una
    # futura refactorización del filtro.
    service, chunk_repo, store, _ = _make_service()
    estructurado = Chunk(
        project_id="p1", source_id="s1", chunk_index=0,
        text="| codigo | nombre |\n| --- | --- |\n| ISC | Ingeniería en Sistemas |",
        token_count=10, section_title="Programas", chunk_type=ChunkType.ESTRUCTURADO,
        structured_content={"columnas": ["codigo", "nombre"], "filas": [{"codigo": "ISC", "nombre": "Ingeniería en Sistemas"}]},
    )
    chunk_repo.save_many("p1", [estructurado])

    n = service.index_source("p1", "s1")
    assert n == 1
    assert store.count("p1") == 1
    indexed_ids = {point.id for point in store._points["p1"][DEFAULT_COLLECTION_NAME].values()}
    assert estructurado.id in indexed_ids


# ---------- query_structured (Pista B.2b del ADR-003) ----------

def test_query_structured_filters_rows_from_estructurado_chunks_only():
    service, chunk_repo, _, _ = _make_service()
    estructurado = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="tabla", token_count=1,
        section_title="Programas", chunk_type=ChunkType.ESTRUCTURADO,
        structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}, {"codigo": "LAE"}]},
    )
    texto = Chunk(
        project_id="p1", source_id="s1", chunk_index=1, text="un párrafo cualquiera", token_count=3,
    )
    chunk_repo.save_many("p1", [estructurado, texto])

    result = service.query_structured("p1", filters=[StructuredFilter(column="codigo", operator="==", value="ISC")])
    assert len(result.rows) == 1
    assert result.rows[0].values == {"codigo": "ISC"}
    assert result.rows[0].section_title == "Programas"
    assert result.rows[0].row_index == 0


def test_query_structured_row_index_reflects_position_within_the_block():
    # Pista C.2a del ADR-003: row_index es lo único que distingue dos
    # filas con los mismos valores -- sin filtro, deben conservar su
    # posición original dentro de "filas".
    service, chunk_repo, _, _ = _make_service()
    estructurado = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="tabla", token_count=1,
        section_title="Programas", chunk_type=ChunkType.ESTRUCTURADO,
        structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}, {"codigo": "LAE"}]},
    )
    chunk_repo.save_many("p1", [estructurado])

    result = service.query_structured("p1")

    assert [row.row_index for row in result.rows] == [0, 1]
    assert [row.values["codigo"] for row in result.rows] == ["ISC", "LAE"]


def test_query_structured_returns_empty_result_without_any_estructurado_chunk():
    # Sección 3.4 del diseño: sin bloques estructurados (fuente no
    # XLSX/CSV, o extraída antes de esta capacidad) -- resultado vacío,
    # no un error.
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="texto plano", token_count=2),
    ])
    result = service.query_structured("p1")
    assert result.rows == []
    assert result.aggregation is None


def test_query_structured_with_aggregation_groups_across_multiple_chunks():
    service, chunk_repo, _, _ = _make_service()
    hoja_1 = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="tabla 1", token_count=1,
        section_title="Programas", chunk_type=ChunkType.ESTRUCTURADO,
        structured_content={
            "columnas": ["plantel", "matricula"],
            "filas": [{"plantel": "Mérida", "matricula": "100"}, {"plantel": "Progreso", "matricula": "30"}],
        },
    )
    hoja_2 = Chunk(
        project_id="p1", source_id="s2", chunk_index=0, text="tabla 2", token_count=1,
        section_title="Extensión", chunk_type=ChunkType.ESTRUCTURADO,
        structured_content={"columnas": ["plantel", "matricula"], "filas": [{"plantel": "Mérida", "matricula": "50"}]},
    )
    chunk_repo.save_many("p1", [hoja_1])
    chunk_repo.save_many("p1", [hoja_2])

    result = service.query_structured(
        "p1", aggregation=StructuredAggregation(function="sum", column="matricula", group_by="plantel"),
    )
    by_group = {b.group_value: b.value for b in result.aggregation}
    assert by_group == {"Mérida": 150.0, "Progreso": 30.0}


def test_query_structured_scoped_to_a_single_source():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="s1", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]},
        ),
        Chunk(
            project_id="p1", source_id="s2", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "LAE"}]},
        ),
    ])
    result = service.query_structured("p1", source_id="s1")
    assert [r.values["codigo"] for r in result.rows] == ["ISC"]


# ---------- query_structured: only_usable_sources/max_access_level
# (auditoria profunda posterior a la Ronda 76 -- ver bitacora: esta via
# se sumo un round despues de que la Ronda 27/B.3 enhebrara estos dos
# filtros en search/search_text/search_hybrid, y nunca los recibio) ----------

def test_query_structured_raises_clear_error_when_only_usable_sources_requested_without_source_repository():
    service, _, _, _ = _make_service()  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        service.query_structured("p1", only_usable_sources=True)


def test_query_structured_raises_clear_error_when_max_access_level_requested_without_source_repository():
    service, _, _, _ = _make_service()  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        service.query_structured("p1", max_access_level=AccessLevel.PUBLICO)


def test_query_structured_max_access_level_excludes_rows_from_a_source_above_the_ceiling():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="publica", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]},
        ),
        Chunk(
            project_id="p1", source_id="confidencial", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "LAE"}]},
        ),
    ])
    source_repo.save(Source(
        id="publica", project_id="p1", title="Pública", source_type=SourceType.XLSX,
        access_level=AccessLevel.PUBLICO,
    ))
    source_repo.save(Source(
        id="confidencial", project_id="p1", title="Confidencial", source_type=SourceType.XLSX,
        access_level=AccessLevel.CONFIDENCIAL,
    ))

    result = service.query_structured("p1", max_access_level=AccessLevel.INTERNO)
    assert [r.values["codigo"] for r in result.rows] == ["ISC"]


def test_query_structured_only_usable_sources_excludes_rejected_source():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="valida", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]},
        ),
        Chunk(
            project_id="p1", source_id="rechazada", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "LAE"}]},
        ),
    ])
    source_repo.save(Source(
        id="valida", project_id="p1", title="Válida", source_type=SourceType.XLSX,
        validation_status=SourceValidationStatus.VALIDADO,
    ))
    source_repo.save(Source(
        id="rechazada", project_id="p1", title="Rechazada", source_type=SourceType.XLSX,
        validation_status=SourceValidationStatus.RECHAZADO,
    ))

    result = service.query_structured("p1", only_usable_sources=True)
    assert [r.values["codigo"] for r in result.rows] == ["ISC"]


def test_query_structured_without_filters_returns_everything_even_with_source_repository_configured():
    # Opt-in, igual que en search/search_text/search_hybrid: tener
    # source_repository configurado no cambia nada sin pedir el filtro.
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="rechazada", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "LAE"}]},
        ),
    ])
    source_repo.save(Source(
        id="rechazada", project_id="p1", title="Rechazada", source_type=SourceType.XLSX,
        validation_status=SourceValidationStatus.RECHAZADO,
    ))

    result = service.query_structured("p1")
    assert [r.values["codigo"] for r in result.rows] == ["LAE"]


def test_query_structured_from_text_parses_filters_and_aggregation():
    # Conveniencia para ui/ingestion/panel.py (regla de capa del panel:
    # solo llama a application, nunca importa domain directamente) --
    # texto plano en vez de StructuredFilter/StructuredAggregation.
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="s1", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={
                "columnas": ["plantel", "matricula"],
                "filas": [{"plantel": "Mérida", "matricula": "100"}, {"plantel": "Progreso", "matricula": "30"}],
            },
        ),
    ])
    result = service.query_structured_from_text(
        "p1", filters_text="matricula > 50",
        aggregation_function="sum", aggregation_column="matricula", group_by="plantel",
    )
    assert [r.values["plantel"] for r in result.rows] == ["Mérida"]
    assert {b.group_value: b.value for b in result.aggregation} == {"Mérida": 100.0}


def test_query_structured_from_text_without_aggregation_function_skips_aggregation():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(
            project_id="p1", source_id="s1", chunk_index=0, text="tabla", token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO,
            structured_content={"columnas": ["codigo"], "filas": [{"codigo": "ISC"}]},
        ),
    ])
    result = service.query_structured_from_text("p1")
    assert len(result.rows) == 1
    assert result.aggregation is None


def test_query_structured_from_text_raises_clear_error_on_malformed_filter_line():
    service, _, _, _ = _make_service()
    with pytest.raises(ValueError, match="Filtro inválido"):
        service.query_structured_from_text("p1", filters_text="columna_sin_operador_ni_valor")


def test_query_structured_from_text_raises_clear_error_on_unsupported_operator():
    service, _, _, _ = _make_service()
    with pytest.raises(ValueError, match="Filtro inválido"):
        service.query_structured_from_text("p1", filters_text="plantel ~= Mérida")


def test_query_structured_from_text_raises_clear_error_on_aggregation_missing_column():
    service, _, _, _ = _make_service()
    with pytest.raises(ValueError, match="Agregación inválida"):
        service.query_structured_from_text("p1", aggregation_function="sum")


def test_reindexing_with_a_different_embedding_dimension_raises_clear_error():
    chunk_repo = InMemoryChunkRepository()
    store = FakeVectorStore()
    index_info_repo = InMemoryIndexInfoRepository()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="texto", token_count=1),
    ])

    service_4d = RagService(chunk_repo, FakeEmbeddingProvider(dimensions=4), store, index_info_repo)
    service_4d.index_source("p1", "s1")
    assert store.count("p1") == 1

    # Mismo VectorStore (mismo índice físico), pero con un modelo de
    # otra dimensión: debe fallar de forma clara, no silenciosa ni
    # con vectores mezclados sin sentido.
    service_8d = RagService(chunk_repo, FakeEmbeddingProvider(dimensions=8), store, index_info_repo)
    with pytest.raises(EmbeddingDimensionMismatchError):
        service_8d.index_source("p1", "s1")

    # Auditoría profunda (ronda posterior a la 76, ver bitácora): antes
    # de esa ronda, IndexSource.execute() borraba los vectores VIEJOS
    # de la fuente antes de calcular los nuevos -- si ensure_collection
    # fallaba (como aquí, por el cambio de dimensión), la fuente
    # quedaba con CERO vectores, peor que antes de pedir el reindexado.
    # El vector original (dimensión 4) debe seguir intacto: el intento
    # fallido de reindexar con otro perfil no debe borrar nada.
    assert store.count("p1") == 1


# ---------- has_low_relevance (hallazgo real: buscar "Tiempo" en un
# plan de estudios sin relacion tematica devolvia resultados con score
# bajo, sin forma de que el usuario supiera si eso era correcto) ----------

def _fake_results(*scores: float) -> list[SemanticSearchResult]:
    return [
        SemanticSearchResult(
            chunk=Chunk(project_id="p1", source_id="s1", chunk_index=i, text="x", token_count=1),
            score=score,
        )
        for i, score in enumerate(scores)
    ]


def test_has_low_relevance_true_when_best_score_below_threshold():
    service, _, _, _ = _make_service()
    assert service.has_low_relevance(_fake_results(0.14, 0.28)) is True


def test_has_low_relevance_false_when_best_score_meets_threshold():
    service, _, _, _ = _make_service()
    assert service.has_low_relevance(_fake_results(0.14, RagService.MIN_RELEVANT_SCORE)) is False


def test_has_low_relevance_false_for_no_results():
    service, _, _, _ = _make_service()
    assert service.has_low_relevance([]) is False


def test_has_low_relevance_respects_custom_min_score():
    service, _, _, _ = _make_service()
    assert service.has_low_relevance(_fake_results(0.5), min_score=0.6) is True
    assert service.has_low_relevance(_fake_results(0.5), min_score=0.4) is False


# ---------- comparador de modelos de embeddings A vs B (capacidad
# opcional: sin embedding_provider_factory, se comporta exactamente
# como antes de esta funcionalidad) ----------

def test_available_embedding_profiles_is_empty_by_default():
    service, _, _, _ = _make_service()
    assert service.available_embedding_profiles() == []


def test_available_embedding_profiles_returns_the_configured_list():
    chunk_repo = InMemoryChunkRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        embedding_provider_factory=lambda profile: FakeEmbeddingProvider(),
        available_embedding_profiles=["perfil_a", "perfil_b"],
    )
    assert service.available_embedding_profiles() == ["perfil_a", "perfil_b"]


def test_compare_profiles_raises_clear_error_without_provider_factory():
    service, _, _, _ = _make_service()  # sin embedding_provider_factory
    with pytest.raises(EmbeddingProfileComparisonUnavailableError):
        service.compare_profiles("p1", "consulta", "perfil_a", "perfil_b")


def test_compare_profiles_delegates_to_the_configured_factory():
    chunk_repo = InMemoryChunkRepository()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme", token_count=3),
    ])

    def factory(profile: str) -> FakeEmbeddingProvider:
        dims = 4 if profile == "perfil_a" else 8
        return FakeEmbeddingProvider(dimensions=dims, model_name=profile)

    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        embedding_provider_factory=factory,
    )

    result_a, result_b = service.compare_profiles("p1", "el gato", "perfil_a", "perfil_b")

    assert result_a.profile == "perfil_a"
    assert result_a.dimensions == 4
    assert result_b.profile == "perfil_b"
    assert result_b.dimensions == 8


# ---------- only_usable_sources: no usar documentos rechazados,
# vencidos o no validados (documento maestro, "supuestos prohibidos")
# ----------

def _validated_source(source_id: str, project_id: str = "p1") -> Source:
    return Source(
        id=source_id, project_id=project_id, title=f"Fuente {source_id}", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.VALIDADO,
    )


def test_search_raises_clear_error_when_only_usable_sources_requested_without_source_repository():
    service, _, _, _ = _make_service()  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        service.search("p1", "consulta", only_usable_sources=True)


def test_search_only_usable_sources_excludes_rejected_and_expired_and_unvalidated():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="validado", chunk_index=0, text="contenido validado y vigente", token_count=4),
        Chunk(project_id="p1", source_id="rechazado", chunk_index=0, text="contenido rechazado", token_count=2),
        Chunk(project_id="p1", source_id="vencido", chunk_index=0, text="contenido vencido", token_count=2),
        Chunk(project_id="p1", source_id="borrador", chunk_index=0, text="contenido en borrador", token_count=3),
    ])
    source_repo.save(_validated_source("validado"))
    source_repo.save(Source(
        id="rechazado", project_id="p1", title="Rechazada", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.RECHAZADO,
    ))
    source_repo.save(Source(
        id="vencido", project_id="p1", title="Vencida", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.VALIDADO, valid_to=date.today() - timedelta(days=1),
    ))
    source_repo.save(Source(
        id="borrador", project_id="p1", title="En borrador", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.BORRADOR,
    ))
    service.index_source("p1", "validado")
    service.index_source("p1", "rechazado")
    service.index_source("p1", "vencido")
    service.index_source("p1", "borrador")

    results = service.search("p1", "contenido", limit=10, only_usable_sources=True)
    assert [r.chunk.source_id for r in results] == ["validado"]


def test_search_without_only_usable_sources_returns_everything_even_with_source_repository_configured():
    # El filtro es opt-in (only_usable_sources=False por defecto):
    # tener source_repository configurado no cambia el comportamiento
    # existente de quien no pide el filtro explícitamente.
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="rechazado", chunk_index=0, text="contenido rechazado", token_count=2),
    ])
    source_repo.save(Source(
        id="rechazado", project_id="p1", title="Rechazada", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.RECHAZADO,
    ))
    service.index_source("p1", "rechazado")

    results = service.search("p1", "contenido", limit=10)
    assert len(results) == 1


def test_search_text_ranks_by_bm25():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="el perro corre en el parque", token_count=6),
    ])
    results = service.search_text("p1", "gato", limit=10)
    assert len(results) == 1
    assert results[0].chunk.source_id == "s1"


def test_search_text_raises_clear_error_when_only_usable_sources_requested_without_source_repository():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme", token_count=3),
    ])
    with pytest.raises(SourceFilterUnavailableError):
        service.search_text("p1", "gato", only_usable_sources=True)


def test_search_hybrid_combines_semantic_and_text_results():
    service, chunk_repo, store, _ = _make_service()
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="un tema sin relación", token_count=4),
    ]
    chunk_repo.save_many("p1", chunks)
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")

    results = service.search_hybrid("p1", "el gato duerme en la casa", limit=5)
    assert results[0].chunk.source_id == "s1"


# ---------- ADR-003, Pista A.2: reranking real opcional en
# RagService.search_hybrid (mismo patrón de "capacidad opcional" que
# embedding_provider_factory/source_repository/only_usable_sources) ----------

def test_has_reranker_is_false_by_default():
    service, _, _, _ = _make_service()
    assert service.has_reranker is False


def test_has_reranker_is_true_when_configured():
    chunk_repo = InMemoryChunkRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        reranker=FakeReranker(),
    )
    assert service.has_reranker is True


def test_search_hybrid_rerank_raises_clear_error_without_reranker_configured():
    service, _, _, _ = _make_service()  # sin reranker
    with pytest.raises(RerankerUnavailableError):
        service.search_hybrid("p1", "cualquier cosa", rerank=True)


def test_search_hybrid_rerank_delegates_to_the_configured_reranker():
    chunk_repo = InMemoryChunkRepository()
    embedder = FakeEmbeddingProvider()
    store = FakeVectorStore()
    reranker = FakeReranker()
    service = RagService(
        chunk_repo, embedder, store, InMemoryIndexInfoRepository(), reranker=reranker,
    )
    query_text = "el gato duerme en la casa"
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="contenido relevante sobre gato", token_count=4),
    ])
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")

    without_rerank = service.search_hybrid("p1", query_text, limit=5)
    assert without_rerank[0].chunk.source_id == "s1"

    with_rerank = service.search_hybrid("p1", query_text, limit=5, rerank=True)
    assert with_rerank[0].chunk.source_id == "s2"


def test_search_only_usable_sources_treats_orphaned_chunk_source_as_not_usable():
    # El punto/fragmento existe pero su Source ya no está en el
    # repositorio (se eliminó por fuera de la app) -- lo más seguro es
    # tratarlo como no usable, no como "usable por defecto".
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()  # vacío a propósito
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="huerfano", chunk_index=0, text="contenido huérfano", token_count=2),
    ])
    service.index_source("p1", "huerfano")

    results = service.search("p1", "contenido", limit=10, only_usable_sources=True)
    assert results == []


# ---------- max_access_level: control de acceso en tiempo de consulta
# (Pista B.3 del ADR-003) ----------

def test_search_raises_clear_error_when_max_access_level_requested_without_source_repository():
    service, _, _, _ = _make_service()  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        service.search("p1", "consulta", max_access_level=AccessLevel.PUBLICO)


def test_search_max_access_level_excludes_sources_above_the_ceiling():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="publica", chunk_index=0, text="contenido publico", token_count=2),
        Chunk(project_id="p1", source_id="confidencial", chunk_index=0, text="contenido confidencial", token_count=2),
    ])
    source_repo.save(Source(
        id="publica", project_id="p1", title="Pública", source_type=SourceType.TXT,
        access_level=AccessLevel.PUBLICO,
    ))
    source_repo.save(Source(
        id="confidencial", project_id="p1", title="Confidencial", source_type=SourceType.TXT,
        access_level=AccessLevel.CONFIDENCIAL,
    ))
    service.index_source("p1", "publica")
    service.index_source("p1", "confidencial")

    results = service.search("p1", "contenido", limit=10, max_access_level=AccessLevel.INTERNO)
    assert [r.chunk.source_id for r in results] == ["publica"]


def test_search_without_max_access_level_returns_everything_even_with_source_repository_configured():
    # El filtro es opt-in (max_access_level=None por defecto): tener
    # source_repository configurado no cambia el comportamiento
    # existente de quien no pide ningún techo -- mismo criterio que
    # only_usable_sources.
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="confidencial", chunk_index=0, text="contenido confidencial", token_count=2),
    ])
    source_repo.save(Source(
        id="confidencial", project_id="p1", title="Confidencial", source_type=SourceType.TXT,
        access_level=AccessLevel.CONFIDENCIAL,
    ))
    service.index_source("p1", "confidencial")

    results = service.search("p1", "contenido", limit=10)
    assert len(results) == 1


def test_search_max_access_level_treats_orphaned_chunk_source_as_exceeding_the_ceiling():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()  # vacío a propósito
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="huerfano", chunk_index=0, text="contenido huérfano", token_count=2),
    ])
    service.index_source("p1", "huerfano")

    results = service.search("p1", "contenido", limit=10, max_access_level=AccessLevel.RESTRINGIDO)
    assert results == []


def test_search_text_max_access_level_excludes_sources_above_the_ceiling():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme", token_count=3),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="el gato come", token_count=3),
    ])
    source_repo.save(Source(
        id="s1", project_id="p1", title="Pública", source_type=SourceType.TXT, access_level=AccessLevel.PUBLICO,
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Restringida", source_type=SourceType.TXT,
        access_level=AccessLevel.RESTRINGIDO,
    ))

    results = service.search_text("p1", "gato", limit=10, max_access_level=AccessLevel.PUBLICO)
    assert [r.chunk.source_id for r in results] == ["s1"]


def test_search_hybrid_max_access_level_is_forwarded_to_both_semantic_and_text():
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    service = RagService(
        chunk_repo, FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
        source_repository=source_repo,
    )
    query_text = "el gato duerme en la casa"
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text=query_text, token_count=6),
    ])
    source_repo.save(Source(
        id="s1", project_id="p1", title="Pública", source_type=SourceType.TXT, access_level=AccessLevel.PUBLICO,
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Restringida", source_type=SourceType.TXT,
        access_level=AccessLevel.RESTRINGIDO,
    ))
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")

    results = service.search_hybrid("p1", query_text, limit=10, max_access_level=AccessLevel.PUBLICO)
    assert [r.chunk.source_id for r in results] == ["s1"]


# ---------- Pista B.1 del ADR-003: expand_to_parent en recuperación ----------

def test_search_expand_to_parent_attaches_parent_without_replacing_matched_chunk():
    service, chunk_repo, _, _ = _make_service()
    padre = Chunk(
        project_id="p1", source_id="s1", chunk_index=1,
        text="Sección completa: extracto puntual de la sección más contenido adicional de contexto",
        token_count=10, section_title="Sección B", chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="extracto puntual de la sección",
        token_count=5, section_title="Sección B", parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [padre, hijo])
    service.index_source("p1", "s1")  # solo `hijo` se indexa (padre excluido, ver IndexSource)

    # Sin pedirlo, el comportamiento no cambia respecto a antes de esta ronda.
    default = service.search("p1", "extracto puntual de la sección", limit=5)
    assert len(default) == 1
    assert default[0].chunk.id == hijo.id
    assert default[0].parent_chunk is None

    expanded = service.search("p1", "extracto puntual de la sección", limit=5, expand_to_parent=True)
    assert len(expanded) == 1
    # El chunk encontrado NUNCA se reemplaza -- se adjunta el padre aparte.
    assert expanded[0].chunk.id == hijo.id
    assert expanded[0].parent_chunk is not None
    assert expanded[0].parent_chunk.id == padre.id
    assert expanded[0].parent_chunk.text == padre.text


def test_search_expand_to_parent_leaves_parent_chunk_none_when_chunk_has_no_parent():
    service, chunk_repo, _, _ = _make_service()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="fragmento sin jerarquía", token_count=3),
    ])
    service.index_source("p1", "s1")

    results = service.search("p1", "fragmento sin jerarquía", limit=5, expand_to_parent=True)
    assert len(results) == 1
    assert results[0].parent_chunk is None


def test_search_text_expand_to_parent_attaches_parent_and_excludes_padre_from_results():
    service, chunk_repo, _, _ = _make_service()
    padre = Chunk(
        project_id="p1", source_id="s1", chunk_index=1,
        text="resumen sin la palabra clave de la consulta", token_count=6,
        chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa",
        token_count=6, parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [padre, hijo])

    # El padre nunca aparece como resultado propio (mismo criterio que
    # IndexSource: nunca compite contra sus propios hijos).
    default = service.search_text("p1", "gato", limit=5)
    assert [r.chunk.id for r in default] == [hijo.id]

    expanded = service.search_text("p1", "gato", limit=5, expand_to_parent=True)
    assert len(expanded) == 1
    assert expanded[0].chunk.id == hijo.id
    assert expanded[0].parent_chunk is not None
    assert expanded[0].parent_chunk.id == padre.id


def test_search_hybrid_expand_to_parent_preserves_parent_chunk_through_rrf():
    service, chunk_repo, store, _ = _make_service()
    padre = Chunk(
        project_id="p1", source_id="s1", chunk_index=1,
        text="Sección completa sobre el gato que duerme en la casa, con más contexto alrededor",
        token_count=14, chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa",
        token_count=6, parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [padre, hijo])
    service.index_source("p1", "s1")

    results = service.search_hybrid("p1", "el gato duerme en la casa", limit=5, expand_to_parent=True)
    assert len(results) == 1
    assert results[0].chunk.id == hijo.id
    assert results[0].parent_chunk is not None
    assert results[0].parent_chunk.id == padre.id


def test_search_hybrid_expand_to_parent_also_preserved_with_rerank():
    chunk_repo = InMemoryChunkRepository()
    embedder = FakeEmbeddingProvider()
    store = FakeVectorStore()
    reranker = FakeReranker()
    service = RagService(
        chunk_repo, embedder, store, InMemoryIndexInfoRepository(), reranker=reranker,
    )
    query_text = "el gato duerme en la casa"
    padre = Chunk(
        project_id="p1", source_id="s2", chunk_index=1,
        text="Sección completa: contenido relevante sobre gato con más contexto",
        token_count=10, chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s2", chunk_index=0, text="contenido relevante sobre gato",
        token_count=4, parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        padre, hijo,
    ])
    service.index_source("p1", "s1")
    service.index_source("p1", "s2")

    with_rerank = service.search_hybrid(
        "p1", query_text, limit=5, rerank=True, expand_to_parent=True,
    )
    winner = next(r for r in with_rerank if r.chunk.id == hijo.id)
    assert winner.parent_chunk is not None
    assert winner.parent_chunk.id == padre.id


# ---------- index_image_source / search_images (Fase 3 de multimodalidad nativa, RAG 3) ----------

def _make_image_service(with_source_repository: bool = True):
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    embedder = FakeEmbeddingProvider()
    image_embedder = FakeImageEmbeddingProvider()
    store = FakeVectorStore()
    service = RagService(
        chunk_repo, embedder, store, InMemoryIndexInfoRepository(),
        source_repository=source_repo if with_source_repository else None,
        image_embedding_provider=image_embedder,
    )
    return service, chunk_repo, source_repo, store, image_embedder


def test_index_image_source_raises_when_service_has_no_image_embedding_provider():
    service, _, _, _ = _make_service()  # sin image_embedding_provider
    with pytest.raises(ImageSearchUnavailableError):
        service.index_image_source("p1", "s1")


def test_search_images_raises_when_service_has_no_image_embedding_provider():
    service, _, _, _ = _make_service()  # sin image_embedding_provider
    with pytest.raises(ImageSearchUnavailableError):
        service.search_images("p1", "foto")


def test_has_image_search_reflects_whether_image_embedding_provider_was_configured():
    without_images, _, _, _ = _make_service()
    with_images, _, _, _, _ = _make_image_service()
    assert without_images.has_image_search is False
    assert with_images.has_image_search is True


def test_index_image_source_requires_source_repository_even_with_image_embedding_provider():
    # A diferencia de index_source, index_image_source necesita leer el
    # Source directamente (Ronda 65, punto 221) -- configurar
    # image_embedding_provider sin source_repository no es suficiente.
    service, _, _, _, _ = _make_image_service(with_source_repository=False)
    with pytest.raises(ImageSearchUnavailableError):
        service.index_image_source("p1", "s1")


def test_search_images_works_without_source_repository_when_filters_not_requested():
    # search_images sí es utilizable sin source_repository -- ese
    # repositorio solo hace falta para los filtros opcionales
    # (only_usable_sources/max_access_level), igual que en `search`.
    service, _, _, _, _ = _make_image_service(with_source_repository=False)
    assert service.search_images("p1", "cualquier cosa", limit=5) == []


def test_search_images_never_embeds_the_query_when_the_project_has_no_image_indexed():
    # Ronda 68 (cierre del vacío 2 de la Ronda 66): interfaces/api/
    # runtime_context.py ahora conecta siempre un image_embedding_provider
    # real (FastEmbedImageProvider) al RagService del runtime HTTP, sin
    # condicionarlo a que el proyecto de verdad tenga fuentes de imagen
    # -- sin este atajo (VectorStore.count() en
    # SemanticSearchImages.execute), CADA mensaje que responde en un
    # proyecto puramente textual pagaría el costo de cargar/descargar el
    # modelo de texto pareado de CLIP. Confirma que embed_query_text
    # nunca se invoca cuando la colección de imágenes está vacía.
    service, _, _, _, image_embedder = _make_image_service()
    results = service.search_images("p1", "cualquier cosa", limit=5)
    assert results == []
    assert image_embedder.embed_query_text_calls == []


def test_search_images_does_embed_the_query_once_the_project_has_at_least_one_image_indexed():
    # Complemento de la prueba anterior: el atajo no debe impedir la
    # búsqueda real una vez que sí hay algo indexado.
    service, _, source_repo, _, image_embedder = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Logo", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/logo.png",
    ))
    service.index_image_source("p1", "s1")

    results = service.search_images("p1", "logo", limit=5)

    assert len(results) == 1
    assert image_embedder.embed_query_text_calls == ["logo"]


def test_index_image_source_raises_source_not_found():
    service, _, source_repo, _, _ = _make_image_service()
    with pytest.raises(SourceNotFoundError):
        service.index_image_source("p1", "s-inexistente")


def test_index_image_source_raises_not_an_image_source_for_wrong_type():
    service, _, source_repo, _, _ = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Un PDF", source_type=SourceType.PDF,
        original_copy_path="/tmp/no-usado.pdf",
    ))
    with pytest.raises(NotAnImageSourceError):
        service.index_image_source("p1", "s1")


def test_index_image_source_returns_zero_without_original_copy_path():
    service, chunk_repo, source_repo, store, image_embedder = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Foto sin copia", source_type=SourceType.IMAGEN_NATIVA,
    ))
    n = service.index_image_source("p1", "s1")
    assert n == 0
    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 0
    assert chunk_repo.list_for_source("p1", "s1") == []


def test_index_image_source_embeds_and_upserts_into_image_collection_only():
    service, chunk_repo, source_repo, store, image_embedder = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Logo", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/s1.png",
    ))
    n = service.index_image_source("p1", "s1")
    assert n == 1
    # Solo la colección de imágenes recibe el punto -- la de texto
    # (DEFAULT_COLLECTION_NAME) queda intacta, mismo criterio de
    # espacios vectoriales separados que Ronda 36.
    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 1
    assert store.count("p1") == 0

    [chunk] = chunk_repo.list_for_source("p1", "s1")
    assert chunk.chunk_type == ChunkType.IMAGEN
    assert chunk.text == ""
    assert chunk.image_relative_path == "s1.png"


def test_index_image_source_keeps_the_old_chunk_and_vector_when_reindexing_fails_on_dimension_mismatch():
    # Auditoría profunda (ronda posterior a la 76, ver bitácora): mismo
    # hallazgo que test_reindexing_with_a_different_embedding_dimension_
    # raises_clear_error, aplicado a IndexImageSource -- antes de esa
    # ronda, el borrado (ChunkRepository + VectorStore) ocurría antes
    # de calcular el embedding nuevo y antes de ensure_collection, así
    # que un cambio de perfil de embeddings de imagen dejaba la fuente
    # con CERO chunks/vectores en vez de conservar los anteriores.
    chunk_repo = InMemoryChunkRepository()
    source_repo = InMemorySourceRepository()
    store = FakeVectorStore()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Logo", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/s1.png",
    ))

    service_4d = RagService(
        chunk_repo, FakeEmbeddingProvider(), store, InMemoryIndexInfoRepository(),
        source_repository=source_repo, image_embedding_provider=FakeImageEmbeddingProvider(dimensions=4),
    )
    service_4d.index_image_source("p1", "s1")
    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 1
    assert len(chunk_repo.list_for_source("p1", "s1")) == 1

    service_8d = RagService(
        chunk_repo, FakeEmbeddingProvider(), store, InMemoryIndexInfoRepository(),
        source_repository=source_repo, image_embedding_provider=FakeImageEmbeddingProvider(dimensions=8),
    )
    with pytest.raises(EmbeddingDimensionMismatchError):
        service_8d.index_image_source("p1", "s1")

    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 1
    assert len(chunk_repo.list_for_source("p1", "s1")) == 1


def test_reindexing_image_source_is_idempotent():
    service, chunk_repo, source_repo, store, image_embedder = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Logo", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/s1.png",
    ))
    service.index_image_source("p1", "s1")
    service.index_image_source("p1", "s1")
    assert store.count("p1", collection=IMAGE_COLLECTION_NAME) == 1
    assert len(chunk_repo.list_for_source("p1", "s1")) == 1


def test_search_images_finds_the_matching_image_by_filename_query():
    # FakeImageEmbeddingProvider (ver fakes_rag.py): embed_images hashea
    # el nombre de archivo sin extensión, embed_query_text hashea el
    # texto de consulta tal cual -- consultar con el mismo texto que el
    # nombre de archivo produce coincidencia exacta (coseno 1.0), sin
    # necesitar ningún modelo CLIP real.
    service, _, source_repo, _, _ = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Logo institucional", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/logo-institucional.png",
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Otra imagen", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/otra-imagen.jpg",
    ))
    service.index_image_source("p1", "s1")
    service.index_image_source("p1", "s2")

    results = service.search_images("p1", "logo-institucional", limit=5)
    assert len(results) == 2
    assert results[0].chunk.source_id == "s1"
    assert results[0].score >= results[1].score


def test_search_images_can_filter_by_source_id():
    service, _, source_repo, _, _ = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Uno", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/uno.png",
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Dos", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/dos.png",
    ))
    service.index_image_source("p1", "s1")
    service.index_image_source("p1", "s2")

    results = service.search_images("p1", "uno", limit=10, source_id="s2")
    assert len(results) == 1
    assert results[0].chunk.source_id == "s2"


def test_search_images_rejects_blank_query():
    service, _, _, _, _ = _make_image_service()
    with pytest.raises(ValueError):
        service.search_images("p1", "   ")


def test_search_images_can_exclude_non_usable_sources():
    service, _, source_repo, _, _ = _make_image_service()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Rechazada", source_type=SourceType.IMAGEN_NATIVA,
        original_copy_path="/proyecto/sources/original/rechazada.png",
        validation_status=SourceValidationStatus.RECHAZADO,
    ))
    service.index_image_source("p1", "s1")

    results = service.search_images("p1", "rechazada", limit=5, only_usable_sources=True)
    assert results == []
