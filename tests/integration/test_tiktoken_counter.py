"""Prueba de integración real de TiktokenCounter -- contra el paquete
`tiktoken` de verdad, no un doble (ítem 7 de la evaluación de madurez
post-8-etapas).

Requiere descargar la codificación la primera vez (ver README,
limitaciones -- mismo patrón que FastEmbedEmbeddingProvider): en un
entorno sin esa conexión, esta prueba se omite explícitamente con un
motivo claro en vez de fallar en rojo o -- peor -- quedar oculta. En
la máquina real del usuario, con acceso a internet, se ejecuta y
valida de verdad."""
from __future__ import annotations

import pytest

from domain.ingestion.exceptions import TokenizerError
from infrastructure.tokenization.tiktoken_counter import TiktokenCounter


@pytest.fixture
def real_counter():
    return TiktokenCounter()


def _skip_if_no_network(exc: TokenizerError) -> None:
    pytest.skip(f"tiktoken no pudo descargar su codificación (sin red en este entorno): {exc}")


def test_count_tokens_returns_a_positive_real_token_count(real_counter):
    try:
        count = real_counter.count_tokens("hola, esto es una prueba de tokenización real!")
    except TokenizerError as exc:
        _skip_if_no_network(exc)
        return
    assert count > 0
    # Con puntuación y varias palabras, un tokenizador BPE real casi
    # siempre produce MÁS tokens que palabras separadas por espacio
    # (la coma y el signo de exclamación suelen ser tokens propios) --
    # confirma que de verdad es un conteo distinto a word_count.
    word_count_approx = len("hola, esto es una prueba de tokenización real!".split())
    assert count >= word_count_approx


def test_count_tokens_empty_string_is_zero(real_counter):
    assert real_counter.count_tokens("") == 0


def test_count_tokens_is_consistent_across_calls(real_counter):
    try:
        first = real_counter.count_tokens("el reglamento de admisión")
        second = real_counter.count_tokens("el reglamento de admisión")
    except TokenizerError as exc:
        _skip_if_no_network(exc)
        return
    assert first == second


# ---------- rutas sin red (no requieren descarga real) ----------

def test_count_tokens_raises_tokenizer_error_when_tiktoken_not_installed(monkeypatch):
    import builtins

    counter = TiktokenCounter()
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("simulado: tiktoken no instalado")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    with pytest.raises(TokenizerError, match="tiktoken"):
        counter.count_tokens("hola")


def test_count_tokens_raises_tokenizer_error_when_encoding_fails_to_load(monkeypatch):
    import tiktoken

    counter = TiktokenCounter()

    def _fake_get_encoding(name):
        raise RuntimeError("simulado: sin conexión para descargar la codificación")

    monkeypatch.setattr(tiktoken, "get_encoding", _fake_get_encoding)
    with pytest.raises(TokenizerError, match="cl100k_base"):
        counter.count_tokens("hola")


def test_encoding_is_loaded_only_once(monkeypatch):
    """_ensure_loaded no debe volver a llamar a tiktoken.get_encoding en
    llamadas posteriores (carga perezosa, una sola vez -- mismo
    criterio que FastEmbedEmbeddingProvider._ensure_loaded)."""
    import tiktoken

    calls = []
    real_get_encoding = tiktoken.get_encoding

    def _counting_get_encoding(name):
        calls.append(name)
        return real_get_encoding(name)

    counter = TiktokenCounter()
    monkeypatch.setattr(tiktoken, "get_encoding", _counting_get_encoding)

    try:
        counter.count_tokens("uno")
        counter.count_tokens("dos")
    except TokenizerError as exc:
        _skip_if_no_network(exc)
        return
    assert len(calls) == 1
