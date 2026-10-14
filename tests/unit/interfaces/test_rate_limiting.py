"""Pruebas unitarias de RateLimiter (Ronda 11, ver
Validacion_observaciones_RAG_STUDIO.md) -- lógica pura de ventana
deslizante, sin FastAPI ni red; el uso real contra el endpoint vive en
tests/integration/test_runtime_api_rate_limiting.py."""
from __future__ import annotations

import time

import pytest

from interfaces.api.rate_limiting import RateLimiter


def test_allows_requests_up_to_the_configured_max():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)

    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-1") is False


def test_rejected_requests_are_not_counted_against_the_quota():
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)

    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-1") is False
    assert limiter.allow("visitante-1") is False  # sigue rechazando, no "gastó" cupo de más


def test_different_keys_have_independent_quotas():
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)

    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-2") is True  # otra clave, su propia cuota
    assert limiter.allow("visitante-1") is False
    assert limiter.allow("visitante-2") is False


def test_quota_frees_up_once_the_window_elapses():
    limiter = RateLimiter(max_requests=1, window_seconds=0.05)

    assert limiter.allow("visitante-1") is True
    assert limiter.allow("visitante-1") is False
    time.sleep(0.1)
    assert limiter.allow("visitante-1") is True


def test_retry_after_seconds_is_a_positive_estimate_within_the_window():
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)
    limiter.allow("visitante-1")

    retry_after = limiter.retry_after_seconds("visitante-1")

    assert 1 <= retry_after <= 10


def test_retry_after_seconds_for_an_unknown_key_does_not_raise():
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)

    assert limiter.retry_after_seconds("nunca-visto") == 1


def test_rejects_a_non_positive_max_requests():
    with pytest.raises(ValueError):
        RateLimiter(max_requests=0)


def test_stale_keys_are_swept_from_memory_once_their_window_elapses():
    # Auditoría Ronda 46, hallazgo importante -- crecimiento sin
    # límite: antes de esta corrección, `_hits` nunca perdía una clave
    # aunque su ventana entera hubiera expirado y nadie volviera a
    # llamar a `allow()` con esa misma clave. Con muchas IPs distintas
    # en un proceso de larga duración, el diccionario crecía para
    # siempre.
    limiter = RateLimiter(max_requests=1, window_seconds=0.05)
    limiter.allow("visitante-1")
    assert "visitante-1" in limiter._hits

    time.sleep(0.1)
    limiter.allow("visitante-2")  # dispara la purga oportunista de TODAS las claves

    assert "visitante-1" not in limiter._hits  # su ventana expiró por completo, se elimina
    assert "visitante-2" in limiter._hits  # la clave que sí acaba de tener actividad permanece


def test_sweep_does_not_remove_a_key_with_activity_still_inside_the_window():
    limiter = RateLimiter(max_requests=5, window_seconds=10.0)
    limiter.allow("visitante-1")
    # Fuerza que la purga oportunista no se salte por el límite de
    # "como mucho una vez por window_seconds" -- lo que se quiere
    # probar aquí es que, aun ejecutándose, la purga no borra una
    # clave cuya marca más reciente sigue dentro de la ventana.
    limiter._last_sweep = time.monotonic() - (limiter._window_seconds * 2)

    limiter._sweep_expired_keys_locked(time.monotonic())

    assert "visitante-1" in limiter._hits
