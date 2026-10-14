"""Pruebas unitarias de las entidades puras del contexto Runtime
(Ronda 44, Pista C.5 del ADR-003 -- roadmap de pendientes de RAG 5)."""
from domain.runtime.entities import latency_percentile


def test_latency_percentile_returns_none_for_an_empty_list():
    # Mismo criterio que avg_latency_ms: ausencia de dato, no 0.0.
    assert latency_percentile([], 95) is None


def test_latency_percentile_returns_the_only_value_for_a_single_element_list():
    assert latency_percentile([42.0], 95) == 42.0
    assert latency_percentile([42.0], 99) == 42.0


def test_latency_percentile_uses_the_nearest_rank_method_over_ten_ordered_values():
    # 10 valores 10..100: ceil(0.95*10)=10 -> posición 10 (1-indexada)
    # -> el valor más alto, 100.0. Mismo para p99.
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert latency_percentile(latencies, 95) == 100.0
    assert latency_percentile(latencies, 99) == 100.0
    # p50 (mediana) con 10 valores: ceil(0.5*10)=5 -> el quinto valor, 50.0.
    assert latency_percentile(latencies, 50) == 50.0


def test_latency_percentile_does_not_require_the_input_to_be_pre_sorted():
    latencies = [300.0, 50.0, 100.0]
    assert latency_percentile(latencies, 95) == 300.0
    assert latency_percentile(latencies, 1) == 50.0


def test_latency_percentile_handles_duplicate_values():
    latencies = [100.0, 100.0, 100.0]
    assert latency_percentile(latencies, 95) == 100.0
