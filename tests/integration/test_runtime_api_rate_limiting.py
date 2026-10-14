"""Prueba de integración del límite de tasa opcional en POST /messages
(Ronda 11, ver Validacion_observaciones_RAG_STUDIO.md -- brecha
identificada en el análisis de "grado profesional" del entregable al
cliente: sin esto, el endpoint no tenía ningún freno contra tráfico
excesivo de un solo origen)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.api.app import create_app

from tests.integration.test_runtime_api import _PROJECT_ID, _fake_embedding_provider_factory, _publish_sample_project


def _make_client(installation_dir, **kwargs) -> TestClient:
    app = create_app(
        installation_dir, embedding_provider_factory=_fake_embedding_provider_factory, **kwargs,
    )
    return TestClient(app)


def test_without_a_configured_limit_there_is_no_throttling(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)  # rate_limit_per_minute no configurado

    for _ in range(10):
        response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
        assert response.status_code == 200


def test_exceeding_the_configured_limit_returns_429_with_retry_after(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, rate_limit_per_minute=2)

    first = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
    second = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola de nuevo"})
    third = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "una vez mas"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert int(third.headers["Retry-After"]) >= 1


def test_rate_limit_applies_before_reporting_an_invalid_snapshot(tmp_path):
    # El límite de tasa protege la capacidad del PROCESO, no solo a
    # proyectos con instantánea válida -- también debe frenar tráfico
    # contra un project_id inexistente (p. ej. alguien probando IDs al
    # azar), no solo contra los válidos.
    from infrastructure.filesystem.paths import InstallationPaths

    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    client = _make_client(paths.base_dir, rate_limit_per_minute=1)

    first = client.post("/projects/no-existe/messages", json={"message": "hola"})
    second = client.post("/projects/no-existe/messages", json={"message": "hola"})

    assert first.status_code == 404
    assert second.status_code == 429
