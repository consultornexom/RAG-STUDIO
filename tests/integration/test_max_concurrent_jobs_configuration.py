"""Pruebas del límite de concurrencia configurable de ThreadJobRunner
(ítem 4 de la segunda evaluación de madurez post-8-etapas, ver
bitácora en README) -- mismo patrón de opción (parámetro explícito >
variable de entorno > default) que
test_embedding_profile_configuration.py."""
from __future__ import annotations

from app.bootstrap import bootstrap
from app.configuration import load_settings


def test_load_settings_defaults_to_no_limit():
    settings = load_settings()
    assert settings.max_concurrent_jobs is None


def test_load_settings_explicit_param_overrides_default():
    settings = load_settings(max_concurrent_jobs=2)
    assert settings.max_concurrent_jobs == 2


def test_load_settings_reads_env_var_when_param_not_given(monkeypatch):
    monkeypatch.setenv("RAGSTUDIO_MAX_CONCURRENT_JOBS", "3")
    settings = load_settings()
    assert settings.max_concurrent_jobs == 3


def test_load_settings_explicit_param_takes_precedence_over_env_var(monkeypatch):
    monkeypatch.setenv("RAGSTUDIO_MAX_CONCURRENT_JOBS", "3")
    settings = load_settings(max_concurrent_jobs=1)
    assert settings.max_concurrent_jobs == 1


def test_bootstrap_wires_unlimited_job_runner_by_default(tmp_path):
    context = bootstrap(base_dir=tmp_path / "agent_studio")
    assert context.jobs._runner._slot_semaphore is None


def test_bootstrap_wires_a_bounded_job_runner_when_requested(tmp_path):
    context = bootstrap(base_dir=tmp_path / "agent_studio", max_concurrent_jobs=2)
    assert context.jobs._runner._slot_semaphore is not None
