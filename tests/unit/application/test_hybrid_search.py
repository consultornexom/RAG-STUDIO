"""Pruebas unitarias de HybridSearch (fusión RRF de SemanticSearch +
TextSearch, Etapa 4: búsqueda híbrida; ADR-003 Pista A.2: reranking
real opcional sobre los candidatos ya fusionados)."""
import pytest

from application.rag.queries.hybrid_search import HybridSearch
from application.rag.queries.semantic_search import SemanticSearch
from application.rag.queries.text_search import TextSearch
from domain.ingestion.entities import Chunk, ChunkType
from domain.rag.exceptions import RerankerError, RerankerUnavailableError
from domain.rag.ports import Reranker

from .fakes_ingestion import InMemoryChunkRepository
from .fakes_rag import FakeEmbeddingProvider, FakeReranker, FakeVectorStore


def _build_hybrid(chunk_repo: InMemoryChunkRepository, reranker=None) -> HybridSearch:
    embedder = FakeEmbeddingProvider()
    store = FakeVectorStore()
    semantic = SemanticSearch(embedder, store, chunk_repo)
    text = TextSearch(chunk_repo)
    return HybridSearch(semantic, text, reranker=reranker), embedder, store


def _index(chunk_repo, embedder, store, project_id, chunks) -> None:
    chunk_repo.save_many(project_id, chunks)
    vectors = embedder.embed_texts([c.text for c in chunks])
    from domain.rag.entities import VectorPoint
    store.ensure_collection(project_id, embedder.dimensions)
    store.upsert(project_id, [
        VectorPoint(id=c.id, vector=v, payload={"source_id": c.source_id})
        for c, v in zip(chunks, vectors, strict=True)
    ])


def test_hybrid_search_ranks_a_chunk_appearing_high_in_both_lists_first():
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo)

    query_text = "el gato duerme en la casa"
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="un tema sin ninguna relación", token_count=5),
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    results = hybrid.execute("p1", query_text, limit=5)
    assert results[0].chunk.source_id == "s1"


def test_hybrid_search_returns_a_result_that_only_one_method_finds():
    # FakeEmbeddingProvider deriva vectores de un hash del texto, sin
    # significado semántico real -- así que un fragmento que solo BM25
    # reconoce (coincidencia exacta de palabra) debe seguir apareciendo
    # en el resultado combinado, no desaparecer por no tener buen score
    # semántico.
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo)
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="palabra-clave-exacta presente aquí", token_count=4),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="otro contenido cualquiera", token_count=3),
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    results = hybrid.execute("p1", "palabra-clave-exacta", limit=5)
    assert "s1" in [r.chunk.source_id for r in results]


def test_hybrid_search_respects_limit():
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo)
    chunks = [
        Chunk(project_id="p1", source_id=f"s{i}", chunk_index=0, text="gato gato gato", token_count=3)
        for i in range(5)
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    results = hybrid.execute("p1", "gato", limit=2)
    assert len(results) == 2


def test_hybrid_search_on_project_without_any_match_returns_empty_list():
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo)
    results = hybrid.execute("p1", "cualquier cosa", limit=5)
    assert results == []


# ---------- ADR-003, Pista A.2: reranking real opcional (después de la
# fusión RRF, con un Reranker configurado explícitamente) ----------

def test_hybrid_search_without_reranker_configured_has_reranker_is_false():
    chunk_repo = InMemoryChunkRepository()
    hybrid, _, _ = _build_hybrid(chunk_repo)
    assert hybrid.has_reranker is False


def test_hybrid_search_with_reranker_configured_has_reranker_is_true():
    chunk_repo = InMemoryChunkRepository()
    hybrid, _, _ = _build_hybrid(chunk_repo, reranker=FakeReranker())
    assert hybrid.has_reranker is True


def test_hybrid_search_rerank_true_without_reranker_configured_raises_clear_error():
    chunk_repo = InMemoryChunkRepository()
    hybrid, _, _ = _build_hybrid(chunk_repo)  # sin reranker
    with pytest.raises(RerankerUnavailableError):
        hybrid.execute("p1", "cualquier cosa", limit=5, rerank=True)


def test_hybrid_search_default_behavior_is_unchanged_when_rerank_is_not_requested():
    # Regresión explícita: configurar un Reranker no debe cambiar el
    # resultado de quien no pide rerank=True -- mismo criterio que
    # "capacidad opcional" en el resto del proyecto (embedding_provider_
    # factory, source_repository).
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo, reranker=FakeReranker())
    query_text = "el gato duerme en la casa"
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="contenido relevante sobre gatos", token_count=4),
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    results = hybrid.execute("p1", query_text, limit=5)  # rerank=False por defecto
    assert results[0].chunk.source_id == "s1"


def test_hybrid_search_rerank_reorders_by_reranker_score_instead_of_rrf_fusion():
    chunk_repo = InMemoryChunkRepository()
    reranker = FakeReranker()
    hybrid, embedder, store = _build_hybrid(chunk_repo, reranker=reranker)
    query_text = "el gato duerme en la casa"
    chunks = [
        # Coincide exactamente con la consulta: RRF lo pone primero
        # (mejor score semántico Y mejor score BM25).
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=query_text, token_count=6),
        # Comparte la palabra "gato" (aparece en BM25) pero no
        # coincide exactamente -- RRF lo deja en segundo lugar. Sí
        # contiene la palabra "relevante" que FakeReranker premia.
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="contenido relevante sobre gato", token_count=4),
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    # Sin reranking: confirma el punto de partida (RRF puro) antes de
    # pedir rerank=True -- s1 gana por coincidencia exacta.
    baseline = hybrid.execute("p1", query_text, limit=5, rerank=False)
    assert baseline[0].chunk.source_id == "s1"

    reranked = hybrid.execute("p1", query_text, limit=5, rerank=True)
    assert reranked[0].chunk.source_id == "s2"
    # El Reranker recibió la consulta real y los textos de los
    # candidatos ya fusionados por RRF (no ids ni scores crudos).
    assert reranker.received_query == query_text
    assert set(reranker.received_passages) == {c.text for c in chunks}


class _MismatchedCountReranker(Reranker):
    """Auditoría Ronda 21: doble que viola a propósito el contrato de
    Reranker.score (un puntaje por candidato) -- simula un adaptador de
    un tercero mal implementado, para confirmar que HybridSearch lo
    detecta con un error de dominio claro en vez de dejar que
    zip(strict=True) lance un ValueError crudo."""

    @property
    def model_name(self) -> str:
        return "mismatched-count-reranker"

    def score(self, query_text: str, passages: list[str]) -> list[float]:
        return [0.0] * (len(passages) - 1) if passages else []


def test_hybrid_search_rerank_raises_reranker_error_when_score_count_mismatches_passages():
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo, reranker=_MismatchedCountReranker())
    chunks = [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="gato uno", token_count=2),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="gato dos", token_count=2),
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    with pytest.raises(RerankerError, match="puntaje"):
        hybrid.execute("p1", "gato", limit=5, rerank=True)


def test_hybrid_search_rerank_respects_limit():
    chunk_repo = InMemoryChunkRepository()
    reranker = FakeReranker()
    hybrid, embedder, store = _build_hybrid(chunk_repo, reranker=reranker)
    chunks = [
        Chunk(project_id="p1", source_id=f"s{i}", chunk_index=0, text="gato gato gato", token_count=3)
        for i in range(5)
    ]
    _index(chunk_repo, embedder, store, "p1", chunks)

    results = hybrid.execute("p1", "gato", limit=2, rerank=True)
    assert len(results) == 2


# ---------- Pista B.1 del ADR-003: expand_to_parent propagado a ambos
# métodos, con y sin reranking ----------

def test_hybrid_search_expand_to_parent_attaches_parent_without_rerank():
    chunk_repo = InMemoryChunkRepository()
    hybrid, embedder, store = _build_hybrid(chunk_repo)
    padre = Chunk(
        project_id="p1", source_id="s1", chunk_index=1,
        text="Sección completa sobre el gato que duerme en la casa, con más contexto",
        token_count=13, chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa",
        token_count=6, parent_chunk_id=padre.id,
    )
    chunk_repo.save_many("p1", [padre])
    _index(chunk_repo, embedder, store, "p1", [hijo])  # solo el hijo se "indexa"

    without_expand = hybrid.execute("p1", "el gato duerme en la casa", limit=5)
    assert without_expand[0].chunk.id == hijo.id
    assert without_expand[0].parent_chunk is None

    expanded = hybrid.execute("p1", "el gato duerme en la casa", limit=5, expand_to_parent=True)
    assert expanded[0].chunk.id == hijo.id
    assert expanded[0].parent_chunk is not None
    assert expanded[0].parent_chunk.id == padre.id
    # El chunk PADRE nunca aparece como resultado propio, ni siquiera
    # con expand_to_parent=True.
    assert all(r.chunk.id != padre.id for r in expanded)


def test_hybrid_search_expand_to_parent_attaches_parent_with_rerank():
    chunk_repo = InMemoryChunkRepository()
    reranker = FakeReranker()
    hybrid, embedder, store = _build_hybrid(chunk_repo, reranker=reranker)
    padre = Chunk(
        project_id="p1", source_id="s2", chunk_index=1,
        text="Sección completa: contenido relevante sobre gato con más contexto",
        token_count=10, chunk_type=ChunkType.PADRE,
    )
    hijo = Chunk(
        project_id="p1", source_id="s2", chunk_index=0, text="contenido relevante sobre gato",
        token_count=4, parent_chunk_id=padre.id,
    )
    otro = Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6)
    chunk_repo.save_many("p1", [padre])
    _index(chunk_repo, embedder, store, "p1", [otro, hijo])

    reranked = hybrid.execute(
        "p1", "el gato duerme en la casa", limit=5, rerank=True, expand_to_parent=True,
    )
    winner = next(r for r in reranked if r.chunk.id == hijo.id)
    assert winner.parent_chunk is not None
    assert winner.parent_chunk.id == padre.id
