"""Prueba de integracion real de FastEmbedEmbeddingProvider -- contra
el paquete fastembed de verdad, no un doble.

Requiere descargar el modelo de Hugging Face la primera vez (ver
README, limitaciones): en un entorno sin esa conexion, esta prueba se
omite explicitamente con un motivo claro en vez de fallar en rojo o
--peor-- quedar oculta. En la maquina real del usuario, con acceso a
internet, se ejecuta y valida de verdad."""
from __future__ import annotations

import pytest

from domain.rag.exceptions import EmbeddingProviderError
from infrastructure.embeddings.fastembed_provider import (
    PERFIL_ASIMETRICO_E5_LARGE,
    PERFIL_SIMETRICO,
    FastEmbedEmbeddingProvider,
    make_multilingual_e5_large_provider,
    make_provider_for_profile,
)


@pytest.fixture
def real_provider(tmp_path):
    return FastEmbedEmbeddingProvider(cache_dir=tmp_path / "models")


def _skip_if_no_network(exc: EmbeddingProviderError) -> None:
    pytest.skip(
        f"FastEmbed no pudo descargar el modelo (sin red hacia Hugging Face en este "
        f"entorno): {exc}"
    )


def test_embed_texts_returns_one_vector_per_text_with_consistent_dimension(real_provider):
    try:
        vectors = real_provider.embed_texts(["hola mundo", "reglamento de admisión"])
    except EmbeddingProviderError as exc:
        _skip_if_no_network(exc)
        return
    assert len(vectors) == 2
    assert len(vectors[0]) == real_provider.dimensions
    assert len(vectors[1]) == real_provider.dimensions


def test_similar_spanish_texts_are_closer_than_unrelated_ones(real_provider):
    try:
        vectors = real_provider.embed_texts([
            "el reglamento de admisión exige boleta de calificaciones",
            "los requisitos de ingreso incluyen la boleta de notas",
            "el gato duerme en el jardín todo el día",
        ])
    except EmbeddingProviderError as exc:
        _skip_if_no_network(exc)
        return

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb)

    sim_related = cosine(vectors[0], vectors[1])
    sim_unrelated = cosine(vectors[0], vectors[2])
    assert sim_related > sim_unrelated


def test_embed_texts_with_empty_list_returns_empty_list(real_provider):
    assert real_provider.embed_texts([]) == []


# ---------- prefijos query:/passage: (modelos asimétricos) ----------
# Estas pruebas no requieren red: sustituyen _ensure_loaded por un
# modelo falso y solo verifican qué texto se le manda a embed(), que es
# donde vive toda la lógica nueva (embed_texts/embed_query aplicando
# passage_prefix/query_prefix). El comportamiento del modelo real
# (intfloat/multilingual-e5-large) se valida por separado en el
# experimento de comparación (ver bitácora 2026-07-26).

class _FakeVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class _FakeModel:
    def __init__(self):
        self.received_texts: list[str] = []

    def embed(self, texts):
        self.received_texts.extend(texts)
        return [_FakeVector([0.0, 0.0]) for _ in texts]


def test_default_provider_has_no_prefixes_symmetric_behavior_unchanged(monkeypatch):
    provider = FastEmbedEmbeddingProvider()
    fake_model = _FakeModel()
    monkeypatch.setattr(provider, "_ensure_loaded", lambda: fake_model)

    provider.embed_texts(["hola", "mundo"])
    provider.embed_query("hola")

    assert fake_model.received_texts == ["hola", "mundo", "hola"]


def test_embed_texts_applies_passage_prefix_when_configured(monkeypatch):
    provider = FastEmbedEmbeddingProvider(passage_prefix="passage: ")
    fake_model = _FakeModel()
    monkeypatch.setattr(provider, "_ensure_loaded", lambda: fake_model)

    provider.embed_texts(["hola", "mundo"])

    assert fake_model.received_texts == ["passage: hola", "passage: mundo"]


def test_embed_query_applies_query_prefix_when_configured(monkeypatch):
    provider = FastEmbedEmbeddingProvider(query_prefix="query: ")
    fake_model = _FakeModel()
    monkeypatch.setattr(provider, "_ensure_loaded", lambda: fake_model)

    provider.embed_query("¿qué materias hay?")

    assert fake_model.received_texts == ["query: ¿qué materias hay?"]


def test_embed_query_default_delegates_to_embed_texts_for_symmetric_models():
    """Ver domain.rag.ports.EmbeddingProvider.embed_query: el default de
    la clase base delega en embed_texts. FastEmbedEmbeddingProvider lo
    sobreescribe, pero con prefijos vacíos (modelo simétrico) el
    resultado debe ser idéntico a embed_texts([text])[0]."""
    provider = FastEmbedEmbeddingProvider()
    fake_model = _FakeModel()
    import types
    provider._ensure_loaded = types.MethodType(lambda self: fake_model, provider)

    [via_embed_texts] = provider.embed_texts(["hola"])
    via_embed_query = provider.embed_query("hola")
    assert via_embed_query == via_embed_texts


def test_make_multilingual_e5_large_provider_uses_expected_model_and_prefixes(monkeypatch):
    provider = make_multilingual_e5_large_provider()
    assert provider.model_name == "intfloat/multilingual-e5-large"

    fake_model = _FakeModel()
    monkeypatch.setattr(provider, "_ensure_loaded", lambda: fake_model)

    provider.embed_texts(["contenido de un fragmento"])
    provider.embed_query("¿qué materias se llevan?")

    assert fake_model.received_texts == [
        "passage: contenido de un fragmento",
        "query: ¿qué materias se llevan?",
    ]


# ---------- make_provider_for_profile (ver README, bitácora
# 2026-07-26: el usuario decidió dejar el modelo asimétrico como
# opción configurable, no como nuevo default) ----------

def test_make_provider_for_profile_default_is_simetrico():
    provider = make_provider_for_profile()
    assert provider.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_make_provider_for_profile_simetrico_explicito():
    provider = make_provider_for_profile(PERFIL_SIMETRICO)
    assert provider.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_make_provider_for_profile_asimetrico_e5_large():
    provider = make_provider_for_profile(PERFIL_ASIMETRICO_E5_LARGE)
    assert provider.model_name == "intfloat/multilingual-e5-large"


def test_make_provider_for_profile_perfil_desconocido_lanza_error_claro():
    with pytest.raises(ValueError, match="simetrico"):
        make_provider_for_profile("no-existe")
