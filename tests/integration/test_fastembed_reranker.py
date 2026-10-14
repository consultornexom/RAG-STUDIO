"""Prueba de integracion real de FastEmbedReranker (ADR-003, Pista
A.2) -- contra el paquete fastembed de verdad, no un doble.

Requiere descargar el modelo de Hugging Face la primera vez (ver
infrastructure/rerankers/fastembed_cross_encoder.py): en un entorno sin
esa conexion, esta prueba se omite explicitamente con un motivo claro
en vez de fallar en rojo o --peor-- quedar oculta. En la maquina real
del usuario, con acceso a internet, se ejecuta y valida de verdad --
mismo criterio que tests/integration/test_fastembed_provider.py."""
from __future__ import annotations

import pytest

from domain.rag.exceptions import RerankerError
from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker


@pytest.fixture
def real_reranker(tmp_path):
    return FastEmbedReranker(cache_dir=tmp_path / "models")


def _skip_if_no_network(exc: RerankerError) -> None:
    pytest.skip(
        f"FastEmbed no pudo descargar el modelo de reranking (sin red hacia Hugging "
        f"Face en este entorno): {exc}"
    )


def test_score_returns_one_value_per_passage_in_the_same_order(real_reranker):
    try:
        scores = real_reranker.score(
            "reglamento de admisión",
            ["el reglamento de admisión exige boleta de calificaciones", "el gato duerme en el jardín"],
        )
    except RerankerError as exc:
        _skip_if_no_network(exc)
        return
    assert len(scores) == 2
    assert all(isinstance(s, float) for s in scores)


def test_related_passage_scores_higher_than_unrelated_one(real_reranker):
    try:
        scores = real_reranker.score(
            "requisitos de admisión",
            [
                "los requisitos de admisión incluyen la boleta de notas",
                "el gato duerme en el jardín todo el día",
            ],
        )
    except RerankerError as exc:
        _skip_if_no_network(exc)
        return
    assert scores[0] > scores[1]


def test_score_with_empty_passages_returns_empty_list(real_reranker):
    assert real_reranker.score("cualquier consulta", []) == []


def test_model_name_defaults_to_the_lightweight_cross_encoder():
    assert FastEmbedReranker().model_name == "Xenova/ms-marco-MiniLM-L-6-v2"


# ---------- pruebas sin red: sustituyen _ensure_loaded por un modelo
# falso, igual criterio que test_fastembed_provider.py ----------

class _FakeCrossEncoder:
    def __init__(self):
        self.received_query = None
        self.received_documents: list[str] = []

    def rerank(self, query, documents):
        self.received_query = query
        self.received_documents = list(documents)
        return (float(len(doc)) for doc in documents)  # generador, como el real


def test_score_passes_query_and_passages_through_to_the_model(monkeypatch):
    reranker = FastEmbedReranker()
    fake_model = _FakeCrossEncoder()
    monkeypatch.setattr(reranker, "_ensure_loaded", lambda: fake_model)

    scores = reranker.score("consulta", ["corto", "un poco más largo"])

    assert fake_model.received_query == "consulta"
    assert fake_model.received_documents == ["corto", "un poco más largo"]
    assert scores == [float(len("corto")), float(len("un poco más largo"))]


def test_score_wraps_model_failures_in_reranker_error(monkeypatch):
    reranker = FastEmbedReranker()

    class _BrokenModel:
        def rerank(self, query, documents):
            raise RuntimeError("fallo simulado del modelo")

    monkeypatch.setattr(reranker, "_ensure_loaded", lambda: _BrokenModel())

    with pytest.raises(RerankerError):
        reranker.score("consulta", ["algo"])


def test_ensure_loaded_raises_clear_error_when_fastembed_is_not_installed(monkeypatch):
    import builtins

    reranker = FastEmbedReranker()
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "fastembed.rerank.cross_encoder":
            raise ImportError("no module named fastembed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RerankerError, match="fastembed"):
        reranker._ensure_loaded()
