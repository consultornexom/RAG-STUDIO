"""Prueba de integración del registro operativo del runtime (Ronda 11,
ver Validacion_observaciones_RAG_STUDIO.md).

Cubre dos cosas a la vez, a propósito: que `interfaces/api/app.py`
efectivamente escribe registros operativos (mensaje atendido, intento
de acceso rechazado), y que la corrección de propagación al logger
raíz en `app/logging_setup.py` funciona de punta a punta a través del
código real (no solo en el repro aislado usado para diagnosticar el
defecto) -- antes de la Ronda 11, ninguno de estos dos registros
llegaba nunca a un archivo, aunque el código que los emite (o uno
equivalente) ya usaba `logging.getLogger(__name__)` correctamente."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.logging_setup import configure_logging
from interfaces.api.app import create_app

from tests.integration.test_runtime_api import _PROJECT_ID, _fake_embedding_provider_factory, _publish_sample_project


def _make_client(installation_dir, **kwargs) -> TestClient:
    app = create_app(
        installation_dir, embedding_provider_factory=_fake_embedding_provider_factory, **kwargs,
    )
    return TestClient(app)


def test_handling_a_message_writes_an_operational_log_entry_without_the_message_text(tmp_path):
    logs_dir = tmp_path / "logs"
    configure_logging(logs_dir, level="INFO")
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    assert response.status_code == 200
    log_id = response.json()["log_id"]

    log_content = (logs_dir / "ragstudio.log").read_text(encoding="utf-8")
    assert "interfaces.api.app" in log_content
    assert "Mensaje atendido" in log_content
    assert log_id in log_content
    assert "responder" in log_content
    # A propósito: nunca el texto real del visitante en este log (ver
    # docstring de post_message) -- eso vive en runtime.db.
    assert "¿cuál es el horario de atención?" not in log_content


def test_a_rejected_credential_is_logged_as_a_warning(tmp_path):
    logs_dir = tmp_path / "logs"
    configure_logging(logs_dir, level="INFO")
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key="secreto-real")

    response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
    assert response.status_code == 401

    log_content = (logs_dir / "ragstudio.log").read_text(encoding="utf-8")
    assert "WARNING" in log_content
    assert _PROJECT_ID in log_content
    assert "secreto-real" not in log_content
