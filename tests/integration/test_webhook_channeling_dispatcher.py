"""Prueba de integración real de WebhookChannelingDispatcher (ADR-002,
Fase 4) -- contra un servidor HTTP real en localhost (no un doble),
mismo criterio que el resto de tests/integration: si algo habla por
red o disco, se prueba contra la cosa real, no contra una simulación
de la cosa real."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from domain.runtime.entities import ChannelingDispatch
from infrastructure.channeling.webhook_dispatcher import ChannelingDispatchError, WebhookChannelingDispatcher

_PAYLOAD = ChannelingDispatch(
    project_id="p1", log_id="log-1", message="quiero hablar con alguien",
    matched_intent="Escalar", code="mesa_ayuda", name="Mesa de ayuda", medium="mesa_ayuda",
    target_area="Soporte", reason="Consulta compleja", user_message="Un asesor te contactará pronto.",
)


class _RecordingHandler(BaseHTTPRequestHandler):
    received: list[tuple[dict, dict]] = []
    response_status = 200
    fail_first_n_requests = 0

    def do_POST(self):  # noqa: N802 -- nombre fijado por BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        _RecordingHandler.received.append((body, dict(self.headers)))
        if len(_RecordingHandler.received) <= _RecordingHandler.fail_first_n_requests:
            self.send_response(500)
        else:
            self.send_response(_RecordingHandler.response_status)
        self.end_headers()

    def log_message(self, *args):  # silencia el log por defecto de BaseHTTPRequestHandler
        pass


@pytest.fixture()
def webhook_server():
    _RecordingHandler.received = []
    _RecordingHandler.response_status = 200
    _RecordingHandler.fail_first_n_requests = 0
    server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _url(server) -> str:
    return f"http://127.0.0.1:{server.server_port}/canalizacion"


def test_dispatch_sends_the_full_payload_as_json(webhook_server):
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server))

    dispatcher.dispatch(_PAYLOAD)

    assert len(_RecordingHandler.received) == 1
    body, _headers = _RecordingHandler.received[0]
    assert body["project_id"] == "p1"
    assert body["code"] == "mesa_ayuda"
    assert body["user_message"] == "Un asesor te contactará pronto."


def test_dispatch_sends_the_configured_secret_as_a_header(webhook_server):
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server), secret="s3cr3t0")

    dispatcher.dispatch(_PAYLOAD)

    _body, headers = _RecordingHandler.received[0]
    assert headers["X-Webhook-Secret"] == "s3cr3t0"


def test_dispatch_without_a_secret_does_not_send_the_header(webhook_server):
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server))

    dispatcher.dispatch(_PAYLOAD)

    _body, headers = _RecordingHandler.received[0]
    assert "X-Webhook-Secret" not in headers


def test_dispatch_raises_when_the_destination_answers_with_an_error(webhook_server):
    _RecordingHandler.response_status = 500
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server))

    with pytest.raises(ChannelingDispatchError):
        dispatcher.dispatch(_PAYLOAD)


def test_dispatch_raises_when_the_destination_is_unreachable():
    dispatcher = WebhookChannelingDispatcher("http://127.0.0.1:1", timeout=1.0, max_attempts=1)

    with pytest.raises(ChannelingDispatchError):
        dispatcher.dispatch(_PAYLOAD)


def test_dispatch_retries_and_succeeds_after_a_transient_failure(webhook_server):
    # Ronda 12: el primer intento falla (blip transitorio), el segundo
    # (reintento) sí llega -- no debe propagar ningún error.
    _RecordingHandler.fail_first_n_requests = 1
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server), max_attempts=2, backoff_seconds=0.01)

    dispatcher.dispatch(_PAYLOAD)  # no debe levantar

    assert len(_RecordingHandler.received) == 2


def test_dispatch_raises_after_exhausting_all_retries(webhook_server):
    _RecordingHandler.fail_first_n_requests = 99  # todos los intentos fallan
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server), max_attempts=3, backoff_seconds=0.01)

    with pytest.raises(ChannelingDispatchError):
        dispatcher.dispatch(_PAYLOAD)

    assert len(_RecordingHandler.received) == 3  # se intentó exactamente max_attempts veces, ni una más ni menos


def test_dispatch_with_a_single_attempt_does_not_retry(webhook_server):
    _RecordingHandler.fail_first_n_requests = 99
    dispatcher = WebhookChannelingDispatcher(_url(webhook_server), max_attempts=1)

    with pytest.raises(ChannelingDispatchError):
        dispatcher.dispatch(_PAYLOAD)

    assert len(_RecordingHandler.received) == 1


def test_rejects_a_max_attempts_below_one():
    with pytest.raises(ValueError):
        WebhookChannelingDispatcher("http://127.0.0.1:1", max_attempts=0)
