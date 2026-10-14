"""Pruebas unitarias del comparador de modelos de embeddings (A vs B)
con dobles de prueba en memoria -- sin red, sin fastembed real."""
import pytest

from application.rag.queries.compare_embedding_profiles import CompareEmbeddingProfiles
from domain.ingestion.entities import Chunk

from .fakes_ingestion import InMemoryChunkRepository
from .fakes_rag import FakeEmbeddingProvider


def _provider_factory(dimensions_by_profile: dict):
    """Fábrica de prueba: un FakeEmbeddingProvider distinto por
    perfil, para poder distinguir en las aserciones cuál perfil
    generó qué resultado (dimensiones/nombre de modelo diferentes)."""
    def factory(profile: str):
        dims, model_name = dimensions_by_profile[profile]
        return FakeEmbeddingProvider(dimensions=dims, provider_name="fake", model_name=model_name)
    return factory


@pytest.fixture
def chunk_repository():
    repo = InMemoryChunkRepository()
    repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text="el gato duerme en la casa", token_count=6),
        Chunk(project_id="p1", source_id="s1", chunk_index=1, text="el perro corre en el parque", token_count=6),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text="contenido de otra fuente", token_count=4),
    ])
    return repo


def test_compare_returns_one_result_per_profile(chunk_repository):
    factory = _provider_factory({"perfil_a": (4, "modelo-a"), "perfil_b": (8, "modelo-b")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    result_a, result_b = comparator.execute("p1", "el gato duerme", "perfil_a", "perfil_b")

    assert result_a.profile == "perfil_a"
    assert result_a.model_name == "modelo-a"
    assert result_a.dimensions == 4
    assert result_b.profile == "perfil_b"
    assert result_b.model_name == "modelo-b"
    assert result_b.dimensions == 8


def test_compare_scopes_to_whole_project_without_source_id(chunk_repository):
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    result_a, _ = comparator.execute("p1", "contenido", "a", "b", limit=10)

    chunk_ids = {r.chunk.id for r in result_a.results}
    all_chunk_ids = {c.id for c in chunk_repository.list_for_project("p1")}
    assert chunk_ids == all_chunk_ids  # las 3 fuentes, no solo una


def test_compare_can_scope_to_a_single_source(chunk_repository):
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    result_a, _ = comparator.execute("p1", "contenido", "a", "b", source_id="s1", limit=10)

    assert all(r.chunk.source_id == "s1" for r in result_a.results)
    assert len(result_a.results) == 2


def test_compare_orders_results_by_score_descending(chunk_repository):
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    result_a, _ = comparator.execute("p1", "el gato duerme en la casa", "a", "b")

    scores = [r.score for r in result_a.results]
    assert scores == sorted(scores, reverse=True)


def test_compare_respects_limit(chunk_repository):
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    result_a, result_b = comparator.execute("p1", "contenido", "a", "b", limit=1)

    assert len(result_a.results) == 1
    assert len(result_b.results) == 1


def test_compare_rejects_blank_query(chunk_repository):
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(chunk_repository, factory)

    with pytest.raises(ValueError):
        comparator.execute("p1", "   ", "a", "b")


def test_compare_on_project_without_chunks_returns_empty_results():
    empty_repo = InMemoryChunkRepository()
    factory = _provider_factory({"a": (4, "m"), "b": (4, "m")})
    comparator = CompareEmbeddingProfiles(empty_repo, factory)

    result_a, result_b = comparator.execute("p-vacio", "cualquier cosa", "a", "b")

    assert result_a.results == []
    assert result_b.results == []
