"""Pruebas unitarias de domain.rag.text_search (BM25 puro, Etapa 4:
búsqueda textual)."""
from domain.rag.text_search import bm25_scores, tokenize


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Hola, Mundo!") == ["hola", "mundo"]


def test_tokenize_empty_text_returns_no_tokens():
    assert tokenize("   ") == []


def test_bm25_scores_ranks_document_covering_more_query_terms_higher():
    # Mismo largo aproximado para los tres documentos, así la
    # diferencia de score refleja cobertura de términos de la
    # consulta, no normalización por longitud.
    documents = [
        "el gato duerme en la casa",       # contiene "gato" y "duerme"
        "el perro corre en el parque",     # no contiene ninguno
        "el gato come en la cocina",       # contiene solo "gato"
    ]
    scores = bm25_scores("gato duerme", documents)
    assert scores[0] > scores[2] > scores[1]
    assert scores[1] == 0.0


def test_bm25_scores_empty_query_returns_all_zeros():
    assert bm25_scores("   ", ["cualquier texto", "otro texto"]) == [0.0, 0.0]


def test_bm25_scores_empty_documents_returns_empty_list():
    assert bm25_scores("consulta", []) == []


def test_bm25_scores_document_without_any_query_term_is_zero():
    scores = bm25_scores("gato", ["perro corre en el parque"])
    assert scores == [0.0]


def test_bm25_scores_handles_documents_with_no_tokens_without_crashing():
    scores = bm25_scores("gato", ["   ", "el gato duerme"])
    assert scores[0] == 0.0
    assert scores[1] > 0.0


def test_bm25_scores_rewards_rarer_terms_more_than_common_ones():
    # "gato" aparece en todos los documentos (poco informativo); "raro"
    # solo en uno -- el documento con el término raro debe salir mejor
    # puntuado, aunque ambos documentos mencionen "gato" igual de veces.
    documents = [
        "el gato duerme en la casa",
        "el gato come en la cocina",
        "el gato raro duerme en la casa",
    ]
    scores = bm25_scores("gato raro", documents)
    assert scores[2] > scores[0]
    assert scores[2] > scores[1]
