"""Fachada de application sobre el JobRunner de workers.

ui llama aquí, nunca importa `workers` directamente (ADR-001, sección 4:
ui solo depende de application). application sí puede depender de
workers: no es un SDK de proveedor externo, es ejecución interna.
"""
from __future__ import annotations

from typing import Callable, Optional

from workers.jobs import JobAlreadyRunningError, JobHandle, ThreadJobRunner, demo_long_task

__all__ = ["BackgroundJobs", "JobAlreadyRunningError"]


class BackgroundJobs:
    def __init__(self, runner: ThreadJobRunner):
        self._runner = runner

    def submit_demo_long_task(self, duration_seconds: float = 3.0, steps: int = 20) -> JobHandle:
        """Tarea de demostración usada para probar que la UI no se bloquea."""
        return self._runner.submit(
            lambda handle: demo_long_task(handle, duration_seconds=duration_seconds, steps=steps)
        )

    def submit_task(self, fn: Callable[[JobHandle], None], *, key: Optional[str] = None) -> JobHandle:
        """Envía cualquier trabajo de application a segundo plano
        (ADR-001, sección 10). `fn` debe llamar únicamente a fachadas de
        application (p. ej. IngestionService), nunca a domain ni
        infrastructure directamente, para no romper la regla de capas
        cuando la UI construye el cierre que se envía aquí.

        `key` (ítem 3 de la segunda evaluación de madurez
        post-8-etapas, ver bitácora): identifica el recurso lógico
        sobre el que trabaja `fn` (p. ej. `f"ingesta:{project_id}:
        {source_id}"`). Si ya hay un trabajo en curso con la misma
        `key`, lanza `JobAlreadyRunningError` de inmediato en vez de
        dejar correr dos trabajos en carrera sobre el mismo recurso.
        Sin `key` (valor por defecto), el comportamiento es exactamente
        el de antes de este ítem: sin deduplicación."""
        return self._runner.submit(fn, key=key)

    def is_key_running(self, key: str) -> bool:
        return self._runner.is_key_running(key)

    def any_running(self) -> bool:
        return self._runner.any_running()

    def get(self, job_id: str):
        return self._runner.get(job_id)
