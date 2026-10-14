"""Límite de tasa mínimo para el runtime de producción (Ronda 11, ver
Validacion_observaciones_RAG_STUDIO.md -- brecha identificada en el
análisis de "grado profesional" del entregable al cliente).

Sin esto, `POST /projects/{id}/messages` no tenía ningún freno: un
token de widget filtrado, o simplemente tráfico anómalo desde un solo
origen, podía saturar el proceso sin límite -- y pesa más porque el
propio diseño ya sirve cada instantánea "un visitante a la vez" (ver
`RuntimeContext`/`LoadedSnapshot.lock`), así que un cliente que manda
solicitudes sin parar bloquea la fila para todos los demás visitantes
legítimos del mismo proyecto.

Deliberadamente una ventana deslizante en memoria, por proceso, sin
ninguna dependencia nueva (mismo criterio que
`infrastructure/channeling/webhook_dispatcher.py`: no se agrega
`slowapi`/`redis` solo para esto) -- suficiente para un solo proceso
protegiéndose a sí mismo. Limitaciones honestas, documentadas en vez
de ocultas:

- Es por IP del visitante (`request.client.host`), no por token de
  widget: cubre el caso más común (un origen que manda tráfico
  excesivo) sin depender de que el visitante haya mandado una
  credencial válida -- un intento de adivinar tokens al azar, cada uno
  distinto, desde la MISMA IP, también queda acotado.
- No protege contra un ataque distribuido desde muchas IPs distintas
  a la vez -- eso es trabajo de la capa de hospedaje (reverse
  proxy/CDN/WAF), ya fuera de alcance de este paquete tal como
  documenta `GUIA_DESPLIEGUE.md` sobre "Hospedaje".
- Se reinicia si el proceso se reinicia (en memoria, no en
  `runtime.db`) -- aceptable: un reinicio ya es una interrupción del
  servicio por sí sola, no hace falta que además recuerde contadores
  de una ventana de un minuto."""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Ventana deslizante simple: como máximo `max_requests` por clave
    en los últimos `window_seconds` segundos. Un solo lock global --
    correcto para el volumen esperado (si esto llegara a ser un cuello
    de botella real, la solución sería particionar por clave, no
    quitar el lock)."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        if max_requests <= 0:
            raise ValueError("max_requests debe ser mayor que cero.")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = {}
        # Auditoría Ronda 46, hallazgo importante -- crecimiento sin
        # límite: `_hits` nunca perdía una clave, ni siquiera una cuyo
        # deque ya quedó vacío tras purgar sus marcas expiradas (eso
        # solo pasa si esa clave nunca vuelve a llamar a `allow()`,
        # así que nada lo disparaba). En un proceso de larga duración
        # con muchas IPs distintas (tráfico legítimo real, no solo un
        # atacante), el diccionario crecía para siempre. `_last_sweep`
        # dispara una purga oportunista de TODAS las claves, no solo
        # la que llega en esta llamada, como mucho una vez por
        # `window_seconds` -- suficientemente barato (recorre el
        # diccionario una sola vez por ventana, no en cada solicitud)
        # y sin ningún hilo de fondo ni dependencia nueva.
        self._last_sweep = time.monotonic()

    def allow(self, key: str) -> bool:
        """True si la solicitud puede pasar (y queda registrada);
        False si `key` ya alcanzó el máximo en la ventana actual (la
        solicitud rechazada NO se cuenta -- no hace falta "gastar"
        cupo para que te digan que no tienes cupo)."""
        now = time.monotonic()
        with self._lock:
            self._sweep_expired_keys_locked(now)
            hits = self._hits.setdefault(key, deque())
            cutoff = now - self._window_seconds
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self._max_requests:
                return False
            hits.append(now)
            return True

    def _sweep_expired_keys_locked(self, now: float) -> None:
        """Debe llamarse con `self._lock` ya adquirido. Purga cada
        deque y elimina del diccionario las claves que quedan vacías
        -- acota el tamaño de `_hits` a las claves con actividad
        reciente, en vez de a todas las que alguna vez existieron."""
        if now - self._last_sweep < self._window_seconds:
            return
        self._last_sweep = now
        cutoff = now - self._window_seconds
        for existing_key in list(self._hits.keys()):
            hits = self._hits[existing_key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if not hits:
                del self._hits[existing_key]

    def retry_after_seconds(self, key: str) -> int:
        """Estimación de cuántos segundos faltan para que la solicitud
        más antigua de la ventana salga de ella -- para el encabezado
        `Retry-After` de la respuesta 429."""
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 1
            remaining = self._window_seconds - (time.monotonic() - hits[0])
            return max(1, int(remaining) + 1)
