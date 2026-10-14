"""Pruebas unitarias de las entidades del contexto RAG (Etapa 4)."""
import pytest
from pydantic import ValidationError

from domain.rag.entities import (
    DEFAULT_COLLECTION_NAME, DEFAULT_MIN_RELEVANT_SCORE, IMAGE_COLLECTION_NAME, IndexInfo, VectorPoint,
    VectorSearchHit, best_relevance_score, cosine_similarity, has_low_relevance,
)


def test_index_info_rejects_non_positive_dimensions():
    with pytest.raises(ValidationError):
        IndexInfo(project_id="p1", embedding_provider="fastembed", embedding_model="m", dimensions=0)


def test_index_info_rejects_negative_points_count():
    with pytest.raises(ValidationError):
        IndexInfo(
            project_id="p1", embedding_provider="fastembed", embedding_model="m",
            dimensions=4, points_count=-1,
        )


def test_index_info_defaults_points_count_to_zero():
    info = IndexInfo(project_id="p1", embedding_provider="fastembed", embedding_model="m", dimensions=4)
    assert info.points_count == 0


def test_vector_point_holds_id_vector_and_payload():
    point = VectorPoint(id="abc", vector=[0.1, 0.2], payload={"source_id": "s1"})
    assert point.id == "abc"
    assert point.vector == [0.1, 0.2]
    assert point.payload == {"source_id": "s1"}


def test_vector_point_payload_defaults_to_empty_dict():
    point = VectorPoint(id="abc", vector=[0.1])
    assert point.payload == {}


def test_vector_search_hit_holds_chunk_id_score_and_payload():
    hit = VectorSearchHit(chunk_id="c1", score=0.87, payload={"source_id": "s1"})
    assert hit.chunk_id == "c1"
    assert hit.score == 0.87
    assert hit.payload == {"source_id": "s1"}


# ---------- umbral de relevancia (hallazgo real: buscar "Tiempo" en un
# plan de estudios sin relacion tematica) ----------

def test_best_relevance_score_returns_the_highest_value():
    assert best_relevance_score([0.14, 0.28, 0.05]) == 0.28


def test_best_relevance_score_returns_none_for_empty_collection():
    assert best_relevance_score([]) is None


def test_has_low_relevance_true_when_best_score_is_below_threshold():
    assert has_low_relevance([0.14, 0.28]) is True


def test_has_low_relevance_false_when_best_score_meets_threshold():
    assert has_low_relevance([0.14, DEFAULT_MIN_RELEVANT_SCORE]) is False


def test_has_low_relevance_false_for_empty_collection():
    # Sin resultados no es "baja relevancia" -- es "sin resultados",
    # un caso distinto que ya maneja la UI por separado.
    assert has_low_relevance([]) is False


def test_has_low_relevance_respects_custom_threshold():
    assert has_low_relevance([0.5], min_score=0.6) is True
    assert has_low_relevance([0.5], min_score=0.4) is False


# ---------- cosine_similarity (comparador de modelos A vs B) ----------

def test_cosine_similarity_of_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_opposite_vectors_is_minus_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_returns_zero_for_a_zero_vector_instead_of_raising():
    # Un vector nulo no tiene direccion -- "sin similitud" es mas
    # razonable que una ZeroDivisionError.
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0


def test_cosine_similarity_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


# ---------- nombres de colección (Fase 3 de multimodalidad nativa, RAG 3) ----------

def test_default_and_image_collection_names_are_distinct():
    # Nunca deben coincidir -- si lo hicieran, indexar imágenes
    # mezclaría vectores de dos espacios no comparables en la misma
    # colección (el riesgo que Fase 3 evita deliberadamente, ver Ronda 36).
    assert DEFAULT_COLLECTION_NAME != IMAGE_COLLECTION_NAME


def test_default_collection_name_matches_historic_value():
    # No debe cambiar sin una migración explícita: es el nombre que ya
    # usan todos los índices Qdrant existentes desde antes de esta ronda.
    assert DEFAULT_COLLECTION_NAME == "chunks"
