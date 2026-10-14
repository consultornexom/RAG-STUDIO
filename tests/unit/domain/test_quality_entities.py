"""Pruebas unitarias de las entidades del contexto Calidad (Etapa 6):
most_severe_verdict y las propiedades computadas de EvaluationRun."""
import pytest

from domain.quality.entities import (
    EvaluationResultItem, EvaluationRun, EvaluationVerdict, RetrievalRegressionStatus, TestCategory,
    compare_retrieval_regression, most_severe_verdict, relative_drop,
)


def _item(verdict: EvaluationVerdict, regressed: bool = False, code: str = "T1") -> EvaluationResultItem:
    return EvaluationResultItem(
        test_case_id="tc1", test_case_code=code, category=TestCategory.RESPUESTA_DIRECTA,
        verdict=verdict, regressed=regressed,
    )


def _retrieval_item(rank, code: str = "T1") -> EvaluationResultItem:
    """ADR-003, Pista A.1: un item cuyo TestCase sí declaraba
    expected_source_id -- `rank` es la posición en la que se encontró
    (o None si nunca apareció entre los resultados)."""
    return EvaluationResultItem(
        test_case_id="tc1", test_case_code=code, category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE, retrieval_check_applicable=True, expected_source_rank=rank,
    )


def test_most_severe_verdict_picks_rojo_over_amarillo_and_verde():
    assert most_severe_verdict([EvaluationVerdict.VERDE, EvaluationVerdict.AMARILLO, EvaluationVerdict.ROJO]) == (
        EvaluationVerdict.ROJO
    )


def test_most_severe_verdict_of_empty_list_is_verde():
    assert most_severe_verdict([]) == EvaluationVerdict.VERDE


def test_evaluation_run_overall_verdict_is_gris_when_no_items():
    run = EvaluationRun(project_id="p1")
    assert run.overall_verdict == EvaluationVerdict.GRIS
    assert run.has_blocking_failures is False


def test_evaluation_run_overall_verdict_is_the_most_severe_among_items():
    run = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE), _item(EvaluationVerdict.AMARILLO)])
    assert run.overall_verdict == EvaluationVerdict.AMARILLO
    assert run.has_blocking_failures is False


def test_evaluation_run_has_blocking_failures_when_any_item_is_rojo():
    run = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE), _item(EvaluationVerdict.ROJO)])
    assert run.has_blocking_failures is True
    assert run.overall_verdict == EvaluationVerdict.ROJO


def test_evaluation_run_regression_count_counts_only_regressed_items():
    run = EvaluationRun(project_id="p1", items=[
        _item(EvaluationVerdict.AMARILLO, regressed=True, code="T1"),
        _item(EvaluationVerdict.VERDE, regressed=False, code="T2"),
        _item(EvaluationVerdict.ROJO, regressed=True, code="T3"),
    ])
    assert run.regression_count == 2


# ---------- ADR-003, Pista A.1: recall_at_k ----------

def test_recall_at_k_is_none_when_no_case_declared_an_expected_source():
    run = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    assert run.recall_at_k(3) is None
    assert run.retrieval_applicable_items == []


def test_recall_at_k_counts_only_cases_within_k_and_ignores_cases_without_a_rank():
    run = EvaluationRun(project_id="p1", items=[
        _retrieval_item(rank=1, code="T1"),  # dentro de k=3
        _retrieval_item(rank=3, code="T2"),  # exactamente en el límite -- cuenta
        _retrieval_item(rank=5, code="T3"),  # fuera de k=3
        _retrieval_item(rank=None, code="T4"),  # nunca apareció en los resultados
        _item(EvaluationVerdict.VERDE, code="T5"),  # no aplica (sin fuente esperada) -- no debe contarse
    ])
    assert run.retrieval_applicable_items == [run.items[0], run.items[1], run.items[2], run.items[3]]
    assert run.recall_at_k(3) == 0.5  # 2 de 4 casos aplicables


def test_recall_at_k_default_is_three():
    run = EvaluationRun(project_id="p1", items=[_retrieval_item(rank=3), _retrieval_item(rank=4)])
    assert run.recall_at_k() == 0.5


# ---------- Ronda 53 (opción A): mean_reciprocal_rank ----------

def test_mean_reciprocal_rank_is_none_when_no_case_declared_an_expected_source():
    run = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    assert run.mean_reciprocal_rank() is None


def test_mean_reciprocal_rank_weighs_position_not_just_presence_within_k():
    run = EvaluationRun(project_id="p1", items=[
        _retrieval_item(rank=1, code="T1"),  # 1.0
        _retrieval_item(rank=2, code="T2"),  # 0.5
        _retrieval_item(rank=None, code="T3"),  # 0.0 -- nunca apareció
    ])
    assert run.mean_reciprocal_rank() == (1.0 + 0.5 + 0.0) / 3


def test_mean_reciprocal_rank_same_denominator_as_recall_at_k():
    run = EvaluationRun(project_id="p1", items=[
        _retrieval_item(rank=1, code="T1"),
        _item(EvaluationVerdict.VERDE, code="T2"),  # no aplica
    ])
    assert run.mean_reciprocal_rank() == 1.0  # promedio sobre 1 caso aplicable, no sobre 2


# ---------- Ronda 53 (opciones B/B'): relative_drop ----------

def test_relative_drop_of_equal_values_is_zero():
    assert relative_drop(0.8, 0.8) == 0.0


def test_relative_drop_reports_the_fractional_decrease():
    assert relative_drop(0.8, 0.6) == pytest.approx(0.25)  # cayó un 25% respecto de 0.8


def test_relative_drop_of_an_improvement_is_zero_not_negative():
    assert relative_drop(0.5, 0.9) == 0.0


def test_relative_drop_reference_zero_returns_zero_instead_of_dividing_by_zero():
    assert relative_drop(0.0, 0.0) == 0.0
    assert relative_drop(0.0, 0.5) == 0.0


# ---------- Ronda 84 (hallazgo real de usuario): compare_retrieval_regression ----------

def test_compare_retrieval_regression_is_sin_metricas_when_the_most_recent_run_has_no_retrieval_items():
    # Ni siquiera importa si la referencia sí tiene métricas -- lo que
    # decide este estado es exclusivamente la corrida más reciente.
    current = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    reference = EvaluationRun(project_id="p1", items=[_retrieval_item(rank=1)])
    comparison = compare_retrieval_regression(current, reference)
    assert comparison.status == RetrievalRegressionStatus.SIN_METRICAS_EN_LA_MAS_RECIENTE
    assert comparison.current_recall is None
    assert comparison.reference_recall is None
    assert comparison.worst_drop is None


def test_compare_retrieval_regression_is_sin_metricas_when_neither_run_has_retrieval_items():
    current = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    reference = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    comparison = compare_retrieval_regression(current, reference)
    assert comparison.status == RetrievalRegressionStatus.SIN_METRICAS_EN_LA_MAS_RECIENTE


def test_compare_retrieval_regression_is_sin_corrida_anterior_when_only_the_most_recent_has_metrics():
    # Este es el reporte real del usuario: la corrida más reciente ya
    # calculó Recall@3/MRR, pero la de referencia no tiene ningún caso
    # con fuente esperada -- el resultado debe distinguir esto de "sin
    # métricas todavía" en vez de decir "ninguna de las dos".
    current = EvaluationRun(project_id="p1", items=[
        _retrieval_item(rank=1, code="T1"), _retrieval_item(rank=2, code="T2"),
        _retrieval_item(rank=1, code="T3"), _retrieval_item(rank=1, code="T4"),
    ])
    reference = EvaluationRun(project_id="p1", items=[_item(EvaluationVerdict.VERDE)])
    comparison = compare_retrieval_regression(current, reference)
    assert comparison.status == RetrievalRegressionStatus.SIN_CORRIDA_ANTERIOR_COMPARABLE
    assert comparison.current_recall == 1.0
    assert comparison.reference_recall is None
    assert comparison.worst_drop is None


def test_compare_retrieval_regression_is_comparable_when_both_runs_have_metrics():
    current = EvaluationRun(project_id="p1", items=[
        _retrieval_item(rank=1, code=f"T{i}") for i in range(3)
    ] + [_retrieval_item(rank=None, code="T3")])
    reference = EvaluationRun(project_id="p1", items=[_retrieval_item(rank=1, code=f"T{i}") for i in range(4)])
    comparison = compare_retrieval_regression(current, reference)
    assert comparison.status == RetrievalRegressionStatus.COMPARABLE
    assert comparison.current_recall == 0.75
    assert comparison.reference_recall == 1.0
    assert comparison.recall_drop == pytest.approx(0.25)
    assert comparison.mrr_drop == pytest.approx(0.25)
    assert comparison.worst_drop == pytest.approx(0.25)
