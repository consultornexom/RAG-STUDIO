"""Pruebas unitarias de TextSearch (búsqueda textual BM25, Etapa 4) con
dobles de prueba en memoria -- sin red, sin Qdrant real, sin fastembed
real: a diferencia de SemanticSearch, ni siquiera necesita indexar."""
import pytest

from application.rag.queries.text_search import TextSearch
from domain.documents.entities import AccessLevel, Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk
from domain.rag.exceptions import SourceFilterUnavailableError

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryChunkRepository


def _chunk_repo_with(*, s1_text: str, s2_text: str) -> InMemoryChunkRepository:
    repo = InMemoryChunkRepository()
    repo.save_many("p1", [
        Chunk(project_id="p1", source_id="s1", chunk_index=0, text=s1_text, token_count=len(s1_text.split())),
        Chunk(project_id="p1", source_id="s2", chunk_index=0, text=s2_text, token_count=len(s2_text.split())),
    ])
    return repo


def test_search_rejects_blank_query():
    search = TextSearch(InMemoryChunkRepository())
    with pytest.raises(ValueError):
        search.execute("p1", "   ")


def test_search_ranks_by_bm25_and_excludes_documents_without_any_match():
    chunk_repo = _chunk_repo_with(
        s1_text="el gato duerme en la casa", s2_text="el perro corre en el parque",
    )
    search = TextSearch(chunk_repo)
    results = search.execute("p1", "gato", limit=10)
    assert len(results) == 1
    assert results[0].chunk.source_id == "s1"


def test_search_on_project_without_matching_chunks_returns_empty_list():
    chunk_repo = _chunk_repo_with(s1_text="contenido uno", s2_text="contenido dos")
    search = TextSearch(chunk_repo)
    assert search.execute("p1", "palabra-inexistente") == []


def test_search_can_scope_to_a_single_source():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    search = TextSearch(chunk_repo)
    results = search.execute("p1", "gato", source_id="s2", limit=10)
    assert len(results) == 1
    assert results[0].chunk.source_id == "s2"


def test_search_respects_limit():
    chunk_repo = InMemoryChunkRepository()
    chunk_repo.save_many("p1", [
        Chunk(project_id="p1", source_id=f"s{i}", chunk_index=0, text="gato gato gato", token_count=3)
        for i in range(5)
    ])
    search = TextSearch(chunk_repo)
    results = search.execute("p1", "gato", limit=2)
    assert len(results) == 2


def test_search_raises_clear_error_when_only_usable_sources_requested_without_source_repository():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    search = TextSearch(chunk_repo)  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        search.execute("p1", "gato", only_usable_sources=True)


def test_search_only_usable_sources_excludes_rejected_source():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    source_repo = InMemorySourceRepository()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Validada", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.VALIDADO,
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Rechazada", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.RECHAZADO,
    ))
    search = TextSearch(chunk_repo, source_repository=source_repo)

    results = search.execute("p1", "gato", limit=10, only_usable_sources=True)
    assert [r.chunk.source_id for r in results] == ["s1"]


# ---------- max_access_level (Pista B.3 del ADR-003) ----------

def test_search_raises_clear_error_when_max_access_level_requested_without_source_repository():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    search = TextSearch(chunk_repo)  # sin source_repository
    with pytest.raises(SourceFilterUnavailableError):
        search.execute("p1", "gato", max_access_level=AccessLevel.PUBLICO)


def test_search_max_access_level_excludes_sources_above_the_ceiling():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    source_repo = InMemorySourceRepository()
    source_repo.save(Source(
        id="s1", project_id="p1", title="Pública", source_type=SourceType.TXT,
        access_level=AccessLevel.PUBLICO,
    ))
    source_repo.save(Source(
        id="s2", project_id="p1", title="Confidencial", source_type=SourceType.TXT,
        access_level=AccessLevel.CONFIDENCIAL,
    ))
    search = TextSearch(chunk_repo, source_repository=source_repo)

    results = search.execute("p1", "gato", limit=10, max_access_level=AccessLevel.INTERNO)
    assert [r.chunk.source_id for r in results] == ["s1"]


def test_search_without_max_access_level_returns_everything_even_with_source_repository_configured():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    source_repo = InMemorySourceRepository()
    source_repo.save(Source(
        id="s2", project_id="p1", title="Confidencial", source_type=SourceType.TXT,
        access_level=AccessLevel.CONFIDENCIAL,
    ))
    search = TextSearch(chunk_repo, source_repository=source_repo)

    results = search.execute("p1", "gato", limit=10)  # max_access_level=None (por defecto)
    assert {r.chunk.source_id for r in results} == {"s1", "s2"}


def test_search_max_access_level_treats_orphaned_chunk_source_as_exceeding_the_ceiling():
    chunk_repo = _chunk_repo_with(s1_text="el gato duerme", s2_text="el gato come")
    source_repo = InMemorySourceRepository()  # s1 y s2 nunca se guardan -- ambas huérfanas.
    search = TextSearch(chunk_repo, source_repository=source_repo)

    results = search.execute("p1", "gato", limit=10, max_access_level=AccessLevel.RESTRINGIDO)
    assert results == []
