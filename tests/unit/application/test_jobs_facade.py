"""Pruebas unitarias de BackgroundJobs (fachada de application sobre
ThreadJobRunner) -- en particular el paso de `key` para deduplicación
(ítem 3 de la segunda evaluación de madurez post-8-etapas, ver
bitácora)."""
from __future__ import annotations

import threading
import time

import pytest

from application.jobs_facade import BackgroundJobs
from workers.jobs import JobAlreadyRunningError, ThreadJobRunner


def test_submit_task_without_key_behaves_like_before_this_item():
    jobs = BackgroundJobs(ThreadJobRunner())
    h1 = jobs.submit_task(lambda h: None)
    h2 = jobs.submit_task(lambda h: None)
    assert h1.id != h2.id


def test_submit_task_with_same_key_while_running_raises_job_already_running_error():
    jobs = BackgroundJobs(ThreadJobRunner())
    started = threading.Event()
    release = threading.Event()

    jobs.submit_task(lambda h: (started.set(), release.wait(timeout=2.0)), key="k1")
    started.wait(timeout=2.0)
    assert jobs.is_key_running("k1") is True

    try:
        with pytest.raises(JobAlreadyRunningError):
            jobs.submit_task(lambda h: None, key="k1")
    finally:
        release.set()


def test_is_key_running_is_false_for_a_key_never_used():
    jobs = BackgroundJobs(ThreadJobRunner())
    assert jobs.is_key_running("nunca-usada") is False


# Auditoría profunda (ronda posterior a la 76, hallazgo O): any_running()
# es lo que permite a MainWindow.closeEvent detectar un trabajo en curso
# sin conocer ninguna `key` -- a diferencia de is_key_running, cubre
# también los trabajos enviados sin `key` (p. ej. búsquedas, consultas
# estructuradas, comparaciones, simulaciones: ver ui/ingestion/panel.py y
# ui/conversational/panel.py).
def test_any_running_is_false_when_no_job_has_ever_been_submitted():
    jobs = BackgroundJobs(ThreadJobRunner())
    assert jobs.any_running() is False


def test_any_running_is_true_while_a_job_without_key_is_still_executing():
    jobs = BackgroundJobs(ThreadJobRunner())
    started = threading.Event()
    release = threading.Event()

    jobs.submit_task(lambda h: (started.set(), release.wait(timeout=2.0)))
    started.wait(timeout=2.0)
    try:
        assert jobs.any_running() is True
    finally:
        release.set()


def test_any_running_is_false_again_once_the_job_finishes():
    jobs = BackgroundJobs(ThreadJobRunner())
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def _run(handle):
        started.set()
        release.wait(timeout=2.0)
        finished.set()

    jobs.submit_task(_run)
    started.wait(timeout=2.0)
    release.set()
    finished.wait(timeout=2.0)
    # El estado se actualiza a COMPLETADO dentro del hilo justo después de
    # que `fn` retorna; darle un instante evita una carrera con la
    # aserción de abajo.
    time.sleep(0.05)
    assert jobs.any_running() is False
