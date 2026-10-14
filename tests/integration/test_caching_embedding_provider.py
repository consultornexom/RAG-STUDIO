"""Pruebas de CachingEmbeddingProvider (Ronda 19) -- con un
EmbeddingProvider en memoria (nada de red ni del paquete fastembed
real; ver test_fastembed_provider.py para la cobertura contra el
modelo real). Vive en tests/integration/ por convención de este
proyecto (mismo criterio que test_fastembed_provider.py: pruebas de un
adaptador de infrastructure), aunque no necesita ningún recurso
externo."""
from __future__ import annotations

from domain.rag.ports import EmbeddingProvider
from infrastructure.embeddings.caching_provider import CachingEmbeddingProvider


class _CountingEmbeddingProvider(EmbeddingProvider):
    """Doble que registra cuántas veces se le pidió embeber cada texto
    -- para poder afirmar que el caché de verdad evita recalcular, no
    solo que devuelve el mismo valor."""

    def __init__(self):
        self.embed_texts_calls: list[list[str]] = []
        self.embed_query_calls: list[str] = []

    @property
    def provider_name(self) -> str:
        return "doble-de-prueba"

    @property
    def model_name(self) -> str:
        return "modelo-de-prueba"

    @property
    def dimensions(self) -> int:
        return 3

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embed_texts_calls.append(list(texts))
        return [[float(len(text)), 0.0, 0.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.embed_query_calls.append(text)
        return [float(len(text)), 1.0, 0.0]


def test_embed_query_calls_the_wrapped_provider_only_once_for_a_repeated_query():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    first = cache.embed_query("¿cuál es el horario de atención?")
    second = cache.embed_query("¿cuál es el horario de atención?")

    assert first == second
    assert wrapped.embed_query_calls == ["¿cuál es el horario de atención?"]  # una sola llamada real
    assert cache.hits == 1
    assert cache.misses == 1


def test_embed_query_recalculates_for_a_genuinely_different_query():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    cache.embed_query("¿cuál es el horario de atención?")
    cache.embed_query("¿cómo me inscribo?")

    assert wrapped.embed_query_calls == ["¿cuál es el horario de atención?", "¿cómo me inscribo?"]
    assert cache.misses == 2
    assert cache.hits == 0


def test_embed_query_normalizes_surrounding_whitespace_before_using_the_cache_key():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    cache.embed_query("¿cuál es el horario?")
    cache.embed_query("  ¿cuál es el horario?  \n")

    assert len(wrapped.embed_query_calls) == 1
    assert cache.hits == 1


def test_embed_query_is_case_sensitive_and_does_not_collapse_distinct_queries():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    cache.embed_query("Campus Norte")
    cache.embed_query("campus norte")

    assert len(wrapped.embed_query_calls) == 2
    assert cache.hits == 0


def test_embed_texts_is_never_cached_and_always_delegates():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    cache.embed_texts(["fragmento uno"])
    cache.embed_texts(["fragmento uno"])

    assert wrapped.embed_texts_calls == [["fragmento uno"], ["fragmento uno"]]  # sin caché, dos llamadas reales


def test_properties_delegate_to_the_wrapped_provider():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    assert cache.provider_name == "doble-de-prueba"
    assert cache.model_name == "modelo-de-prueba"
    assert cache.dimensions == 3


def test_the_lru_eviction_discards_the_least_recently_used_entry_once_full():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped, max_entries=2)

    cache.embed_query("uno")
    cache.embed_query("dos")
    cache.embed_query("tres")  # debe desalojar "uno" (el menos recientemente usado)

    wrapped.embed_query_calls.clear()
    cache.embed_query("uno")  # tuvo que recalcularse -- ya no estaba
    cache.embed_query("tres")  # este sí seguía en el caché

    assert wrapped.embed_query_calls == ["uno"]


def test_using_a_cached_entry_protects_it_from_eviction():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped, max_entries=2)

    cache.embed_query("uno")
    cache.embed_query("dos")
    cache.embed_query("uno")  # reutilizarla la vuelve "reciente" de nuevo
    cache.embed_query("tres")  # ahora debe desalojar "dos", no "uno"

    wrapped.embed_query_calls.clear()
    cache.embed_query("uno")

    assert wrapped.embed_query_calls == []  # sigue en el caché, no se recalculó


def test_cache_info_reports_entries_hits_and_misses():
    wrapped = _CountingEmbeddingProvider()
    cache = CachingEmbeddingProvider(wrapped)

    cache.embed_query("uno")
    cache.embed_query("uno")
    cache.embed_query("dos")

    info = cache.cache_info()
    assert info == {"entries": 2, "hits": 1, "misses": 2}
