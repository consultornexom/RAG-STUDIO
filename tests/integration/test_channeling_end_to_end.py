"""Prueba de integración real de punta a punta de la canalización
real (ADR-002, Fase 4): un mensaje real que dispara un guardrail de
canalización, a través de `POST /projects/{id}/messages` (FastAPI real
vía TestClient), termina entregando un webhook HTTP real a un servidor
local -- ninguna de las tres capas (API, motor de decisión, entrega)
es un doble aquí."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from domain.conversational.entities import ChannelingScheme, GuardrailRule, Intent, RuleActionType, RuleType
from domain.release.entities import ProjectSnapshot
from domain.runtime.entities import ChannelingDispatch
from domain.runtime.ports import ChannelingDispatcher
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository,
    SqlAlchemyGuardrailRuleRepository,
    SqlAlchemyIntentRepository,
)
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.channeling.webhook_dispatcher import WebhookChannelingDispatcher
from interfaces.api.app import create_app

from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

_PROJECT_ID = "p1"


class _RecordingHandler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.received.append(json.loads(self.rfile.read(length).decode("utf-8")))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture()
def webhook_server():
    _RecordingHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _publish_project_with_a_channeling_guardrail(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    SqlAlchemyIntentRepository(paths).save(Intent(
        project_id=_PROJECT_ID, name="Dar de baja", positive_examples=["quiero darme de baja"],
        fallback_channeling_code="soporte-humano",
    ))
    SqlAlchemyGuardrailRuleRepository(paths).save(GuardrailRule(
        project_id=_PROJECT_ID, name="Riesgo alto siempre se canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[], action=RuleActionType.CANALIZAR,
    ))
    SqlAlchemyChannelingSchemeRepository(paths).save(ChannelingScheme(
        project_id=_PROJECT_ID, code="soporte-humano", name="Soporte humano", medium="ticket",
        target_area="Atención al cliente", user_message="Un asesor te contactará en breve.",
    ))

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )
    return paths


def _fake_embedding_provider_factory(_profile, _cache_dir):
    return WordOverlapFakeEmbeddingProvider()


def test_a_channeling_message_dispatches_a_real_webhook_end_to_end(tmp_path, webhook_server):
    paths = _publish_project_with_a_channeling_guardrail(tmp_path)
    dispatcher = WebhookChannelingDispatcher(f"http://127.0.0.1:{webhook_server.server_port}/canalizacion")
    app = create_app(
        paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory,
        channeling_dispatcher=dispatcher,
    )
    client = TestClient(app)

    response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "quiero darme de baja"})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "canalizar"
    assert body["response_text"] == "Un asesor te contactará en breve."

    assert len(_RecordingHandler.received) == 1
    delivered = _RecordingHandler.received[0]
    assert delivered["project_id"] == _PROJECT_ID
    assert delivered["code"] == "soporte-humano"
    assert delivered["medium"] == "ticket"
    assert delivered["target_area"] == "Atención al cliente"
    assert delivered["log_id"] == body["log_id"]


class _BlockingChannelingDispatcher(ChannelingDispatcher):
    """Bloquea SOLO su primera llamada hasta que el test la libere
    explícitamente (`release_event.set()`) -- la segunda llamada en
    adelante pasa de inmediato. Pensado para probar, de forma
    determinista (sin depender de tiempos de espera arbitrarios), que
    dos solicitudes concurrentes a la MISMA instantánea ya no comparten
    el mismo `loaded.lock` durante la entrega del webhook (auditoría
    Ronda 46, hallazgo #146, corregido en la Ronda 51)."""

    def __init__(self):
        self.calls: list[ChannelingDispatch] = []
        self._calls_lock = threading.Lock()
        self.first_call_started_event = threading.Event()
        self.release_first_call_event = threading.Event()

    def dispatch(self, payload: ChannelingDispatch) -> None:
        with self._calls_lock:
            self.calls.append(payload)
            is_first_call = len(self.calls) == 1
        if is_first_call:
            self.first_call_started_event.set()
            self.release_first_call_event.wait(timeout=10)


def test_a_slow_channeling_dispatch_does_not_block_a_concurrent_message_to_the_same_snapshot(
    tmp_path, webhook_server,
):
    # Auditoría Ronda 46, hallazgo #146, corregido en la Ronda 51:
    # antes de esta corrección, dispatch_channeling() corría DENTRO de
    # `with loaded.lock:` (interfaces/api/app.py) -- el mismo lock que
    # protege el acceso a QdrantLocalVectorStore -- así que un webhook
    # lento o caído en la primera solicitud bloqueaba a cualquier otra
    # solicitud concurrente contra la MISMA instantánea hasta agotar
    # sus reintentos. Esta prueba deja la primera entrega bloqueada a
    # propósito y confirma que una segunda solicitud, disparada mientras
    # la primera sigue "colgada" en el dispatcher, completa igual.
    paths = _publish_project_with_a_channeling_guardrail(tmp_path)
    dispatcher = _BlockingChannelingDispatcher()
    app = create_app(
        paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory,
        channeling_dispatcher=dispatcher,
    )
    client = TestClient(app)

    results: dict[str, tuple[int, float]] = {}

    def _send_first():
        started = time.monotonic()
        response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "quiero darme de baja"})
        results["first"] = (response.status_code, time.monotonic() - started)

    first_thread = threading.Thread(target=_send_first)
    first_thread.start()
    # Espera a que la primera solicitud ya esté "colgada" dentro de
    # dispatch() -- si el lock ya se soltó antes de llegar aquí (el
    # comportamiento corregido), la segunda solicitud no debería
    # heredar ese bloqueo.
    assert dispatcher.first_call_started_event.wait(timeout=10), (
        "la primera solicitud nunca llegó a dispatch_channeling()"
    )

    second_started = time.monotonic()
    second_response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "quiero darme de baja"})
    second_elapsed = time.monotonic() - second_started

    dispatcher.release_first_call_event.set()  # deja terminar a la primera, ya medido lo que importaba
    first_thread.join(timeout=10)
    assert not first_thread.is_alive()

    assert second_response.status_code == 200
    # Generoso a propósito (evitar un falso negativo por carga del
    # entorno de CI) pero muy por debajo del timeout de 10s que
    # mantiene colgada a la primera llamada -- si el lock siguiera
    # compartido, la segunda solicitud tendría que esperar ese mismo
    # tiempo.
    assert second_elapsed < 5.0, (
        f"la segunda solicitud tardó {second_elapsed:.2f}s -- parece haber esperado a la primera entrega"
    )
    assert len(dispatcher.calls) == 2  # ambas solicitudes llegaron a intentar el despacho
    assert results["first"][0] == 200


def test_without_a_dispatcher_configured_canalizar_still_works_but_nothing_is_delivered(tmp_path, webhook_server):
    paths = _publish_project_with_a_channeling_guardrail(tmp_path)
    app = create_app(paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory)
    client = TestClient(app)

    response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "quiero darme de baja"})

    assert response.status_code == 200
    assert response.json()["action"] == "canalizar"
    assert _RecordingHandler.received == []
