import threading
import time

import pytest

from workers.jobs import JobAlreadyRunningError, JobStatus, ThreadJobRunner, demo_long_task


def test_submit_returns_immediately_without_blocking_caller():
    runner = ThreadJobRunner()
    job_duration = 1.0

    start = time.monotonic()
    handle = runner.submit(lambda h: demo_long_task(h, duration_seconds=job_duration, steps=10))
    elapsed_to_return = time.monotonic() - start

    # Este es el criterio de aceptación de la Iteración 1: la llamada que
    # inicia el trabajo debe regresar casi de inmediato, muy por debajo
    # de la duración real de la tarea, para que la UI nunca se congele.
    assert elapsed_to_return < job_duration / 5

    while handle.status in (JobStatus.PENDIENTE, JobStatus.PREPARANDO, JobStatus.EJECUTANDO):
        time.sleep(0.02)
    assert handle.status == JobStatus.COMPLETADO
    assert handle.progress == 1.0


def test_job_can_be_cancelled_mid_flight():
    runner = ThreadJobRunner()
    handle = runner.submit(lambda h: demo_long_task(h, duration_seconds=2.0, steps=40))
    time.sleep(0.1)
    handle.cancel()

    deadline = time.monotonic() + 1.0
    while handle.status not in (JobStatus.CANCELADO, JobStatus.COMPLETADO, JobStatus.FALLIDO):
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)

    assert handle.status == JobStatus.CANCELADO
    assert handle.progress < 1.0


def test_failed_job_reports_error_instead_of_hiding_it():
    runner = ThreadJobRunner()

    def _boom(handle):
        raise RuntimeError("fallo simulado")

    handle = runner.submit(_boom)
    deadline = time.monotonic() + 1.0
    while handle.status == JobStatus.EJECUTANDO and time.monotonic() < deadline:
        time.sleep(0.02)

    assert handle.status == JobStatus.FALLIDO
    assert "fallo simulado" in handle.error


# ---------- deduplicación por key (ítem 3 de la segunda evaluación de madurez) ----------

def test_submit_without_key_never_deduplicates_like_before_this_item():
    runner = ThreadJobRunner()
    h1 = runner.submit(lambda h: demo_long_task(h, duration_seconds=0.3, steps=5))
    h2 = runner.submit(lambda h: demo_long_task(h, duration_seconds=0.3, steps=5))
    assert h1.id != h2.id


def test_submit_with_same_key_while_running_raises_job_already_running_error():
    runner = ThreadJobRunner()
    started = threading.Event()
    release = threading.Event()

    def _blocking(handle):
        started.set()
        release.wait(timeout=2.0)

    runner.submit(_blocking, key="fuente:p1:s1")
    started.wait(timeout=2.0)
    assert runner.is_key_running("fuente:p1:s1") is True

    try:
        with pytest.raises(JobAlreadyRunningError):
            runner.submit(lambda h: None, key="fuente:p1:s1")
    finally:
        release.set()


def test_key_is_released_after_the_job_completes_so_a_new_one_can_start():
    runner = ThreadJobRunner()
    h1 = runner.submit(lambda h: demo_long_task(h, duration_seconds=0.1, steps=2), key="fuente:p1:s1")
    deadline = time.monotonic() + 2.0
    while h1.status in (JobStatus.PENDIENTE, JobStatus.PREPARANDO, JobStatus.EJECUTANDO):
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert h1.status == JobStatus.COMPLETADO
    assert runner.is_key_running("fuente:p1:s1") is False

    # Ya no debe lanzar JobAlreadyRunningError: la clave se liberó.
    h2 = runner.submit(lambda h: None, key="fuente:p1:s1")
    assert h2.id != h1.id


def test_key_is_released_even_when_the_job_fails():
    runner = ThreadJobRunner()

    def _boom(handle):
        raise RuntimeError("fallo simulado")

    h1 = runner.submit(_boom, key="fuente:p1:s1")
    deadline = time.monotonic() + 2.0
    while h1.status == JobStatus.EJECUTANDO and time.monotonic() < deadline:
        time.sleep(0.02)
    assert h1.status == JobStatus.FALLIDO
    assert runner.is_key_running("fuente:p1:s1") is False


def test_different_keys_run_concurrently_without_blocking_each_other():
    runner = ThreadJobRunner()
    started_a = threading.Event()
    started_b = threading.Event()

    def _run_a(handle):
        started_a.set()
        time.sleep(0.1)

    def _run_b(handle):
        started_b.set()
        time.sleep(0.1)

    runner.submit(_run_a, key="fuente:p1:a")
    runner.submit(_run_b, key="fuente:p1:b")
    # Ambos deben poder arrancar sin que uno espere al otro -- claves
    # distintas nunca compiten entre sí.
    assert started_a.wait(timeout=1.0)
    assert started_b.wait(timeout=1.0)


# ---------- max_concurrent_jobs (ítem 4 de la segunda evaluación de madurez) ----------

def test_without_max_concurrent_jobs_all_submitted_jobs_start_immediately():
    runner = ThreadJobRunner()  # sin límite: comportamiento de siempre
    started_a = threading.Event()
    started_b = threading.Event()
    release = threading.Event()

    runner.submit(lambda h: (started_a.set(), release.wait(timeout=2.0)))
    runner.submit(lambda h: (started_b.set(), release.wait(timeout=2.0)))
    try:
        assert started_a.wait(timeout=1.0)
        assert started_b.wait(timeout=1.0)
    finally:
        release.set()


def test_max_concurrent_jobs_limits_how_many_run_at_once():
    runner = ThreadJobRunner(max_concurrent_jobs=1)
    started_a = threading.Event()
    started_b = threading.Event()
    release_a = threading.Event()

    h1 = runner.submit(lambda h: (started_a.set(), release_a.wait(timeout=2.0)))
    started_a.wait(timeout=1.0)

    h2 = runner.submit(lambda h: started_b.set())
    # El segundo trabajo debe quedarse esperando cupo (PENDIENTE), sin
    # arrancar, mientras el primero siga ocupando el único cupo.
    time.sleep(0.2)
    assert started_b.is_set() is False
    assert h2.status == JobStatus.PENDIENTE

    release_a.set()
    deadline = time.monotonic() + 2.0
    while h1.status not in (JobStatus.COMPLETADO, JobStatus.CANCELADO, JobStatus.FALLIDO):
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)
    # Al liberarse el cupo del primero, el segundo debe poder arrancar.
    assert started_b.wait(timeout=2.0)


def test_max_concurrent_jobs_still_respects_key_deduplication():
    runner = ThreadJobRunner(max_concurrent_jobs=5)
    started = threading.Event()
    release = threading.Event()

    runner.submit(lambda h: (started.set(), release.wait(timeout=2.0)), key="k1")
    started.wait(timeout=1.0)
    try:
        with pytest.raises(JobAlreadyRunningError):
            runner.submit(lambda h: None, key="k1")
    finally:
        release.set()
