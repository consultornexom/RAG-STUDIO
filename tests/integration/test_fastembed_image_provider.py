"""Prueba de integracion real de FastEmbedImageProvider -- contra el
paquete fastembed de verdad, no un doble. Fase 1 del diseno de
multimodalidad nativa (ver docs proyecto/RAG_STUDIO_Diseno_Ejecutable_
RAG3_Multimodalidad.docx).

Requiere descargar el modelo de Hugging Face la primera vez (~0.34 GB,
Qdrant/clip-ViT-B-32-vision): en un entorno sin esa conexion, esta
prueba se omite explicitamente con un motivo claro en vez de fallar en
rojo -- mismo criterio que test_fastembed_provider.py."""
from __future__ import annotations

import pytest
from PIL import Image

from domain.rag.exceptions import EmbeddingProviderError
from infrastructure.embeddings.fastembed_image_provider import FastEmbedImageProvider


@pytest.fixture
def real_provider(tmp_path):
    return FastEmbedImageProvider(cache_dir=tmp_path / "models")


def _skip_if_no_network(exc: EmbeddingProviderError) -> None:
    pytest.skip(
        f"FastEmbed no pudo descargar el modelo de imagen (sin red hacia Hugging "
        f"Face en este entorno): {exc}"
    )


def _make_image(path, color) -> str:
    Image.new("RGB", (64, 64), color=color).save(path)
    return str(path)


def test_embed_images_returns_one_vector_per_image_with_consistent_dimension(real_provider, tmp_path):
    red = _make_image(tmp_path / "red.png", (220, 20, 20))
    blue = _make_image(tmp_path / "blue.png", (20, 20, 220))
    try:
        vectors = real_provider.embed_images([red, blue])
    except EmbeddingProviderError as exc:
        _skip_if_no_network(exc)
        return
    assert len(vectors) == 2
    assert len(vectors[0]) == real_provider.dimensions
    assert len(vectors[1]) == real_provider.dimensions


def test_similar_images_are_closer_than_unrelated_ones(real_provider, tmp_path):
    red_a = _make_image(tmp_path / "red_a.png", (220, 20, 20))
    red_b = _make_image(tmp_path / "red_b.png", (200, 30, 30))
    blue = _make_image(tmp_path / "blue.png", (20, 20, 220))
    try:
        vectors = real_provider.embed_images([red_a, red_b, blue])
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


def test_embed_images_with_empty_list_returns_empty_list(real_provider):
    assert real_provider.embed_images([]) == []


def test_provider_name_and_model_name(real_provider):
    assert real_provider.provider_name == "fastembed"
    assert real_provider.model_name == "Qdrant/clip-ViT-B-32-vision"


def test_embed_query_text_returns_a_vector_matching_the_vision_model_dimension(real_provider):
    """Fase 3 del diseño de multimodalidad nativa: embed_query_text usa
    un SEGUNDO modelo (Qdrant/clip-ViT-B-32-text, pareja del modelo de
    imagen por defecto), pero ambos deben producir vectores de la misma
    dimensión (512) para que de verdad compartan el mismo espacio."""
    try:
        vector = real_provider.embed_query_text("una imagen roja")
    except EmbeddingProviderError as exc:
        _skip_if_no_network(exc)
        return
    assert len(vector) == 512


def test_dimensions_before_first_embed_raises_clear_error(real_provider):
    """A diferencia de FastEmbedEmbeddingProvider (que puede forzar un
    embed_texts([""]) barato para calcular dimensions), no hay una
    "imagen vacia" equivalente -- ver domain.rag.ports.
    ImageEmbeddingProvider y el docstring de dimensions en el
    adaptador."""
    with pytest.raises(EmbeddingProviderError, match="todavia no se conocen"):
        _ = real_provider.dimensions


# ---------- pruebas sin red: sustituyen _ensure_loaded por un modelo
# falso, mismo patron que test_fastembed_provider.py ----------

class _FakeVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class _FakeImageModel:
    def __init__(self):
        self.received_paths: list[str] = []

    def embed(self, image_paths):
        self.received_paths.extend(image_paths)
        return [_FakeVector([0.1, 0.2, 0.3]) for _ in image_paths]


def test_embed_images_delegates_to_underlying_model(monkeypatch):
    provider = FastEmbedImageProvider()
    fake_model = _FakeImageModel()
    monkeypatch.setattr(provider, "_ensure_loaded", lambda: fake_model)

    vectors = provider.embed_images(["/tmp/a.png", "/tmp/b.png"])

    assert fake_model.received_paths == ["/tmp/a.png", "/tmp/b.png"]
    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert provider.dimensions == 3


def test_embed_images_wraps_model_failure_in_embedding_provider_error(monkeypatch):
    provider = FastEmbedImageProvider()

    class _BrokenModel:
        def embed(self, image_paths):
            raise RuntimeError("archivo no es una imagen valida")

    monkeypatch.setattr(provider, "_ensure_loaded", lambda: _BrokenModel())

    with pytest.raises(EmbeddingProviderError, match="fallo al generar vectores"):
        provider.embed_images(["/tmp/no-es-imagen.txt"])


def test_missing_fastembed_package_raises_clear_error(monkeypatch):
    import builtins

    provider = FastEmbedImageProvider()
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("no module named fastembed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(EmbeddingProviderError, match="no esta instalado"):
        provider.embed_images(["/tmp/a.png"])


# ---------- embed_query_text (Fase 3 de multimodalidad nativa) --
# pruebas sin red, mismo patron de arriba (modelo de texto pareado
# sustituido por un doble) ----------

class _FakeTextModel:
    def __init__(self):
        self.received_texts: list[str] = []

    def embed(self, texts):
        self.received_texts.extend(texts)
        return [_FakeVector([0.4, 0.5, 0.6]) for _ in texts]


def test_embed_query_text_delegates_to_underlying_text_model(monkeypatch):
    provider = FastEmbedImageProvider()
    fake_model = _FakeTextModel()
    monkeypatch.setattr(provider, "_ensure_text_model_loaded", lambda: fake_model)

    vector = provider.embed_query_text("una consulta en lenguaje natural")

    assert fake_model.received_texts == ["una consulta en lenguaje natural"]
    assert vector == [0.4, 0.5, 0.6]


def test_embed_query_text_wraps_model_failure_in_embedding_provider_error(monkeypatch):
    provider = FastEmbedImageProvider()

    class _BrokenTextModel:
        def embed(self, texts):
            raise RuntimeError("fallo simulado del modelo de texto")

    monkeypatch.setattr(provider, "_ensure_text_model_loaded", lambda: _BrokenTextModel())

    with pytest.raises(EmbeddingProviderError, match="fallo al generar el vector"):
        provider.embed_query_text("una consulta")


def test_embed_query_text_raises_clear_error_for_model_without_known_text_pairing():
    # Qdrant/resnet50-onnx (ver docstring del modulo) no tiene un
    # codificador de texto pareado conocido -- solo sirve para "imagen
    # busca imagen", nunca para "texto busca imagen".
    provider = FastEmbedImageProvider(model_name="Qdrant/resnet50-onnx")
    with pytest.raises(EmbeddingProviderError, match="no tiene un codificador de texto pareado"):
        provider.embed_query_text("una consulta")


def test_embed_query_text_reuses_the_loaded_text_model_across_calls(monkeypatch):
    provider = FastEmbedImageProvider()
    fake_model = _FakeTextModel()
    load_calls = {"n": 0}

    def _fake_ensure_loaded():
        load_calls["n"] += 1
        return fake_model

    monkeypatch.setattr(provider, "_ensure_text_model_loaded", _fake_ensure_loaded)
    provider.embed_query_text("primera consulta")
    provider.embed_query_text("segunda consulta")
    # _ensure_text_model_loaded se llama en cada embed_query_text (igual
    # que _ensure_loaded en embed_images), pero es la propia
    # implementacion real (no este doble) la que cachea el modelo en
    # self._text_model -- este doble solo confirma que ambas llamadas
    # llegan al mismo modelo, no que el modelo se recargue.
    assert load_calls["n"] == 2
    assert fake_model.received_texts == ["primera consulta", "segunda consulta"]


def test_ensure_text_model_loaded_caches_the_model_instance(monkeypatch):
    # A diferencia de la prueba anterior (que sustituye
    # _ensure_text_model_loaded por completo), esta prueba sí ejercita
    # la cache real: solo se sustituye la clase TextEmbedding importada
    # dentro del metodo.
    provider = FastEmbedImageProvider()
    created = []

    class _FakeTextEmbeddingClass:
        def __init__(self, model_name, cache_dir):
            created.append(model_name)

        def embed(self, texts):
            return [_FakeVector([0.1, 0.2]) for _ in texts]

    import fastembed
    monkeypatch.setattr(fastembed, "TextEmbedding", _FakeTextEmbeddingClass)

    provider.embed_query_text("uno")
    provider.embed_query_text("dos")
    assert created == ["Qdrant/clip-ViT-B-32-text"]  # una sola carga, no dos
