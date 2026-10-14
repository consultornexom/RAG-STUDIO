"""Primera integración real de canalización (ADR-002, Fase 4:
"canalización real (correo/CRM/ticket)"), implementada como un
webhook HTTP saliente configurable en vez de un adaptador atado a un
proveedor concreto (SMTP, un CRM propietario...) -- la mayoría de
mesas de ayuda, CRMs y proveedores de correo transaccional aceptan
disparar una acción a partir de un webhook entrante en su propia API,
así que este adaptador cubre "correo/CRM/ticket" sin elegir ninguno
por el usuario ni añadir una dependencia nueva por proveedor.

Un solo destino por proceso para esta primera iteración (mismo
criterio que la Fase 3: "un solo canal en la primera iteración" para
no multiplicar el esfuerzo antes de validar que funciona de punta a
punta) -- enrutar por `ChannelingScheme.code`/`medium` a destinos
distintos queda fuera de esta fase a propósito, ver
Validacion_observaciones_RAG_STUDIO.md.

Usa únicamente `urllib.request` de la biblioteca estándar -- no se
agrega `requests`/`httpx` como dependencia nueva de producción solo
para una sola llamada POST saliente (`httpx` ya está instalado hoy
solo de forma transitiva, por `starlette.testclient`, nunca declarado
como dependencia propia; no es seguro asumir que seguirá ahí).

Reintentos (Ronda 12, ver Validacion_observaciones_RAG_STUDIO.md --
brecha identificada en el análisis de "grado profesional" del
entregable): la mayoría de fallos de un webhook saliente son blips de
red transitorios (un timeout ocasional, una reinicialización del
destino), no una caída sostenida -- un solo intento los trataba igual
que una caída real. `max_attempts` (por defecto 2) reintenta con una
espera corta (`backoff_seconds`, por defecto 0.5s) antes de darse por
vencido. Deliberadamente pocos intentos y una espera corta: esta
llamada ocurre DENTRO de la misma solicitud HTTP del visitante (ver
`HandleIncomingMessage._dispatch_channeling`) -- cada intento adicional
es latencia real para quien espera la respuesta del agente, así que el
límite es un compromiso entre "no tratar un blip como caída" y "no
hacer esperar al visitante más de lo razonable". Si el destino sigue
caído después de agotar los intentos, el fallo se registra con
`logger.exception` en `HandleIncomingMessage` -- desde la corrección
del logger raíz (Ronda 11), eso ya llega de verdad a
`ragstudio-api.log`, que es la forma en que un operador se entera hoy;
una vista consultable de "canalizaciones fallidas" dentro de RAG
STUDIO (más allá de grep sobre el log) queda como posible mejora
futura, no resuelta en esta ronda."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from domain.runtime.entities import ChannelingDispatch
from domain.runtime.ports import ChannelingDispatcher


class ChannelingDispatchError(Exception):
    """La entrega real (HTTP) falló -- red, timeout, o el destino
    respondió con un error, en TODOS los intentos configurados. Quien
    llama (`HandleIncomingMessage`) decide si esto debe romper la
    respuesta al visitante (hoy, no)."""


class WebhookChannelingDispatcher(ChannelingDispatcher):
    def __init__(
        self, url: str, secret: str | None = None, timeout: float = 5.0,
        max_attempts: int = 2, backoff_seconds: float = 0.5,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts debe ser al menos 1.")
        self._url = url
        self._secret = secret
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    def dispatch(self, payload: ChannelingDispatch) -> None:
        last_error: ChannelingDispatchError = ChannelingDispatchError("sin intentos ejecutados")
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._dispatch_once(payload)
                return
            except ChannelingDispatchError as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    time.sleep(self._backoff_seconds)
        raise last_error

    def _dispatch_once(self, payload: ChannelingDispatch) -> None:
        body = json.dumps(payload.model_dump(mode="json")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._secret:
            # Firma simple compartida, no HMAC -- suficiente para que
            # el receptor descarte solicitudes que no vengan de este
            # runtime; si el destino real exige HMAC (p. ej. Slack),
            # ese adaptador específico puede construirse a partir de
            # este mismo puerto sin tocar HandleIncomingMessage.
            headers["X-Webhook-Secret"] = self._secret
        request = urllib.request.Request(self._url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise ChannelingDispatchError(
                        f"El webhook de canalización respondió {response.status}."
                    )
        except urllib.error.HTTPError as exc:
            raise ChannelingDispatchError(
                f"El webhook de canalización respondió {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ChannelingDispatchError(f"No se pudo contactar al webhook de canalización: {exc.reason}") from exc
