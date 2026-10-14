"""Pruebas del perfil de modelo de embeddings configurable (ver
README, bitácora 2026-07-26): el usuario decidió, tras confirmar con
un experimento real que el modelo asimétrico mejora la búsqueda en
lenguaje natural, NO cambiar el default sino dejarlo como opción
explícita -- estas pruebas verifican que ese mecanismo de opción
(parámetro explícito > variable de entorno > default) funciona sin
tocar el comportamiento de quien no lo pide.

No requieren red: la carga real del modelo (descarga de Hugging Face)
es perezosa -- FastEmbedEmbeddingProvider/make_provider_for_profile
solo construyen el objeto, nunca descargan nada hasta el primer
embed_texts/embed_query (ver infrastructure/embeddings/fastembed_provider.py)."""
from __future__ import annotations

from app.bootstrap import bootstrap
from app.configuration import load_settings


def test_load_settings_defaults_to_simetrico_profile():
    settings = load_settings()
    assert settings.embedding_profile == "simetrico"


def test_load_settings_explicit_param_overrides_default():
    settings = load_settings(embedding_profile="asimetrico_e5_large")
    assert settings.embedding_profile == "asimetrico_e5_large"


def test_load_settings_reads_env_var_when_param_not_given(monkeypatch):
    monkeypatch.setenv("RAGSTUDIO_EMBEDDING_PROFILE", "asimetrico_e5_large")
    settings = load_settings()
    assert settings.embedding_profile == "asimetrico_e5_large"


def test_load_settings_explicit_param_takes_precedence_over_env_var(monkeypatch):
    monkeypatch.setenv("RAGSTUDIO_EMBEDDING_PROFILE", "asimetrico_e5_large")
    settings = load_settings(embedding_profile="simetrico")
    assert settings.embedding_profile == "simetrico"


def test_bootstrap_wires_simetrico_provider_by_default(tmp_path):
    context = bootstrap(base_dir=tmp_path / "agent_studio")
    embedder = context.rag_service._index_source._embedder
    assert embedder.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_bootstrap_wires_asimetrico_provider_when_requested(tmp_path):
    context = bootstrap(base_dir=tmp_path / "agent_studio", embedding_profile="asimetrico_e5_large")
    embedder = context.rag_service._index_source._embedder
    assert embedder.model_name == "intfloat/multilingual-e5-large"


def test_bootstrap_raises_clear_error_for_unknown_profile(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="simetrico"):
        bootstrap(base_dir=tmp_path / "agent_studio", embedding_profile="no-existe")
