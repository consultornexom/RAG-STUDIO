"""Administrador de trabajos en segundo plano (ADR-001, sección 10 /
RAG STUDIO.odt, sección 9). La UI solo captura, muestra estado y
cancela; nunca ejecuta trabajo pesado en su propio hilo.
"""
from __future__ import annotations

import logging

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class JobAlreadyRunningError(RuntimeError):
    """Se pidió `ThreadJobRunner.submit(..., key=...)` con una clave que
    ya tiene un trabajo en curso (ítem 3 de la segunda evaluación de
    madurez post-8-etapas, ver bitácora). Antes, nada impedía lanzar
    dos trabajos sobre la misma clave lógica (p. ej. extraer y
    fragmentar la misma fuente) al mismo tiempo -- cada botón de la UI
    se autolimitaba con su propio `_active_job`, pero eso es una
    convención de cada panel, no una garantía del runner: nada la exige
    para quien llame a `application` directamente (un script, una
    prueba, un futuro trabajo por lote). `key` cierra esa brecha en la
    capa correcta."""

    def __init__(self, key: str):
        super().__init__(f"Ya hay un trabajo en curso para {key!r}; espera a que termine.")
        self.key = key


class JobStatus(str, Enum):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    EJECUTANDO = "ejecutando"
    PAUSADO = "pausado"
    COMPLETADO = "completado"
    FALLIDO = "fallido"
    CANCELADO = "cancelado"


@dataclass
class JobHandle:
    id: str
    status: JobStatus = JobStatus.PENDIENTE
    progress: float = 0.0
    error: Optional[str] = None
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()


class ThreadJobRunner:
    """Ejecuta trabajos en un hilo separado para que la UI nunca se
    bloquee. Adecuado para E/S ligera (lectura de archivos, llamadas a
    servicios). El trabajo realmente pesado (OCR, normalización
    intensiva, fragmentación masiva, embeddings) debe ejecutarse en
    procesos separados — ver ProcessJobRunner, marcador para Etapa 3.
    """

    def __init__(self, max_concurrent_jobs: Optional[int] = None):
        """`max_concurrent_jobs` (ítem 4 de la segunda evaluación de
        madurez post-8-etapas, ver bitácora): límite de trabajos
        EJECUTANDO de verdad al mismo tiempo -- parte de lo que pide
        ADR-001 sección 10 ("configurar procesos máximos... de los
        trabajos en segundo plano"). `None` (default) es sin límite: el
        comportamiento exacto de antes de este ítem, cada trabajo
        enviado arranca su hilo de inmediato. Un entero > 0 hace que un
        trabajo que exceda el cupo se quede en `JobStatus.PENDIENTE`
        (ya existía el estado en el enum, pero antes era solo un
        instante fugaz: ahora puede durar mientras se libera un cupo)
        hasta que otro trabajo termine."""
        self._jobs: dict[str, JobHandle] = {}
        self._lock = threading.Lock()
        # Claves lógicas con un trabajo en curso ahora mismo (ítem 3 de
        # la segunda evaluación de madurez post-8-etapas, ver
        # bitácora) -- solo se registran los trabajos que se envían con
        # `key` (un trabajo sin key nunca participa en la
        # deduplicación, igual que antes de este ítem).
        self._running_keys: dict[str, str] = {}  # key -> job_id
        self._slot_semaphore = (
            threading.Semaphore(max_concurrent_jobs) if max_concurrent_jobs else None
        )

    def submit(self, fn: Callable[[JobHandle], None], *, key: Optional[str] = None) -> JobHandle:
        """Envía `fn` a un hilo en segundo plano. Si se pasa `key`, se
        reserva de inmediato (antes de lanzar el hilo) y se libera
        cuando el trabajo termine (completado, cancelado o fallido) --
        un segundo `submit` con la misma `key` mientras la reserva siga
        activa lanza `JobAlreadyRunningError` en el acto, en vez de
        dejar correr dos trabajos en carrera sobre el mismo recurso
        lógico (p. ej. extraer y fragmentar la misma fuente a la vez).

        Si el runner se construyó con `max_concurrent_jobs`, el hilo
        arranca de inmediato (igual que siempre: `submit` nunca
        bloquea al llamador) pero el trabajo se queda esperando en
        `JobStatus.PENDIENTE` un cupo libre antes de pasar a
        PREPARANDO/EJECUTANDO -- el límite de concurrencia real vive
        del lado del hilo en segundo plano, nunca del lado de quien
        llama a `submit`."""
        handle = JobHandle(id=str(uuid.uuid4()))
        with self._lock:
            if key is not None and key in self._running_keys:
                raise JobAlreadyRunningError(key)
            self._jobs[handle.id] = handle
            if key is not None:
                self._running_keys[key] = handle.id

        def _release_key() -> None:
            if key is None:
                return
            with self._lock:
                if self._running_keys.get(key) == handle.id:
                    del self._running_keys[key]

        def _runner() -> None:
            acquired_slot = False
            try:
                if self._slot_semaphore is not None:
                    # handle.status ya es PENDIENTE (default de
                    # JobHandle) mientras se espera un cupo libre.
                    self._slot_semaphore.acquire()
                    acquired_slot = True
                handle.status = JobStatus.PREPARANDO
                handle.status = JobStatus.EJECUTANDO
                try:
                    fn(handle)
                    handle.status = (
                        JobStatus.CANCELADO if handle.is_cancelled() else JobStatus.COMPLETADO
                    )
                    if handle.status == JobStatus.COMPLETADO:
                        handle.progress = 1.0
                except Exception as exc:  # noqa: BLE001 - se registra, nunca se oculta
                    # Ronda 93 (auditoría): nunca un error vacío, y con traza en el
                    # registro. El estado se fija al final (después de registrar),
                    # como antes, para no alargar la ventana entre "FALLIDO" y la
                    # liberación de la clave.
                    logger.exception("Trabajo en segundo plano %s fallido.", handle.id)
                    handle.error = str(exc).strip() or f"{type(exc).__name__} (sin mensaje)"
                    handle.status = JobStatus.FALLIDO
            finally:
                if acquired_slot and self._slot_semaphore is not None:
                    self._slot_semaphore.release()
                _release_key()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return handle

    def get(self, job_id: str) -> Optional[JobHandle]:
        with self._lock:
            return self._jobs.get(job_id)

    def is_key_running(self, key: str) -> bool:
        with self._lock:
            return key in self._running_keys

    def any_running(self) -> bool:
        """True si al menos un trabajo está en PREPARANDO o EJECUTANDO
        ahora mismo, sin importar si se envió con `key` o no (auditoría
        profunda, ronda posterior a la 76, hallazgo O: antes no existía
        ninguna forma de preguntarle al runner "¿hay algo corriendo?" --
        `is_key_running` exige conocer la clave lógica exacta, que la
        ventana principal no tiene por qué conocer. Sin esto, cerrar la
        aplicación mientras un trabajo corre lo abandona en silencio: los
        hilos son `daemon=True`, así que el proceso simplemente termina
        y el trabajo (una ingesta, una reindexación) queda a medias sin
        ningún aviso al usuario)."""
        with self._lock:
            return any(
                handle.status in (JobStatus.PREPARANDO, JobStatus.EJECUTANDO)
                for handle in self._jobs.values()
            )


class ProcessJobRunner:
    """Marcador de extensión para trabajo pesado en procesos separados
    (multiprocessing real, no hilos) -- sigue sin implementarse.

    Nota honesta (ítem 4 de la segunda evaluación de madurez
    post-8-etapas, ver bitácora en README): esta clase existía desde la
    Etapa 1 con un comentario que decía "se implementa junto con el
    orquestador de ingesta (Etapa 3)" -- Etapa 3 (y las etapas 4-8) ya
    se completaron hace tiempo y esto nunca se construyó; el comentario
    quedó desactualizado y aquí se corrige. En la práctica, todo el
    trabajo pesado real de la app (extracción/OCR, fastembed, tiktoken,
    fragmentación) corre hoy en hilos de `ThreadJobRunner`, no en
    procesos separados: Python libera el GIL durante buena parte de ese
    trabajo (E/S de archivos, y las partes en C/C++ de `pypdf`,
    `pytesseract`, `onnxruntime` dentro de `fastembed`, `tiktoken`), así
    que en la práctica hay paralelismo real aunque sea con hilos, no
    procesos puros -- no es una app inutilizable por esto, pero no es
    lo que describe ADR-001 sección 10 (procesos separados,
    configurables en memoria/CPU/GPU/prioridad) tampoco. Implementarlo
    de verdad requeriría resolver cómo pasar `application`/`domain` a
    otro proceso (no son objetos triviales de enviar por
    `multiprocessing` -- sesiones de SQLAlchemy, por ejemplo, no son
    picklables) y rediseñar cómo `JobHandle.cancel()`/`progress` cruzan
    el límite entre procesos; se deja para una iteración futura si el
    volumen de datos reales de un proyecto lo justifica (ver ítem 4,
    que en su lugar acota la concurrencia de hilos con
    `ThreadJobRunner(max_concurrent_jobs=...)`, un paso más barato hacia
    el mismo objetivo de fondo: no competir sin control por CPU/memoria)."""

    def submit(self, fn: Callable, *args, **kwargs) -> JobHandle:  # pragma: no cover
        raise NotImplementedError(
            "ProcessJobRunner todavia no esta implementado (ver bitacora en README, "
            "item 4 de la segunda evaluacion de madurez post-8-etapas): el trabajo pesado "
            "de esta app corre en ThreadJobRunner (hilos), no en procesos separados."
        )


def demo_long_task(handle: JobHandle, duration_seconds: float = 3.0, steps: int = 10) -> None:
    """Tarea de demostración sin utilidad funcional: solo avanza
    progreso y respeta cancelación. Se usa para probar que la interfaz
    permanece responsiva durante una operación larga (criterio de
    aceptación de la Iteración 1)."""
    step_duration = duration_seconds / steps
    for i in range(steps):
        if handle.is_cancelled():
            return
        time.sleep(step_duration)
        handle.progress = (i + 1) / steps
