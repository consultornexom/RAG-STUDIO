"""Prueba de integración real del canal widget web (ADR-002, Fase 3):
GET /widget.js y el CORS configurable que necesita para funcionar
embebido en el sitio de un cliente, distinto del origen de la API.

No repite la cobertura de test_runtime_api.py (esa ya prueba el
endpoint de mensajes de punta a punta contra Qdrant/SQLite reales);
aquí solo se prueba lo nuevo de la Fase 3, con instalaciones vacías
(el 404 de un proyecto sin instantánea es suficiente para ejercitar
las cabeceras CORS de una solicitud real, sin repetir el montaje
completo de un proyecto)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from infrastructure.filesystem.paths import InstallationPaths
from interfaces.api.app import create_app

_ORIGIN = "https://cliente-ejemplo.com"


def _make_client(tmp_path, **kwargs) -> TestClient:
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    app = create_app(paths.base_dir, **kwargs)
    return TestClient(app)


def test_widget_js_is_served_publicly_without_any_authentication(tmp_path):
    client = _make_client(tmp_path, api_key="secreto")

    response = client.get("/widget.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    body = response.text
    assert "/messages" in body
    assert "attachShadow" in body  # aislado del CSS del sitio anfitrión


def test_widget_js_never_requires_the_api_key_even_when_configured(tmp_path):
    client = _make_client(tmp_path, api_key="secreto")

    # A propósito, sin encabezado X-API-Key -- cualquier visitante debe
    # poder descargar el script del widget.
    response = client.get("/widget.js")

    assert response.status_code == 200


def test_cors_is_absent_by_default(tmp_path):
    client = _make_client(tmp_path)

    response = client.post(
        "/projects/no-existe/messages", json={"message": "hola"}, headers={"Origin": _ORIGIN},
    )

    assert response.status_code == 404
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_cors_preflight_allows_the_configured_origin(tmp_path):
    client = _make_client(tmp_path, allowed_origins=[_ORIGIN])

    response = client.options(
        "/projects/p1/messages",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ORIGIN


def test_cors_preflight_rejects_an_origin_not_in_the_allowlist(tmp_path):
    client = _make_client(tmp_path, allowed_origins=[_ORIGIN])

    response = client.options(
        "/projects/p1/messages",
        headers={"Origin": "https://otro-sitio.com", "Access-Control-Request-Method": "POST"},
    )

    # Starlette responde 400 a un preflight de un origen no permitido en
    # vez de omitir la cabecera -- en cualquier caso, el navegador real
    # nunca deja pasar la solicitud siguiente sin la cabecera correcta.
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_post_message_actual_request_includes_the_cors_header_when_configured(tmp_path):
    client = _make_client(tmp_path, allowed_origins=[_ORIGIN])

    response = client.post(
        "/projects/no-existe/messages", json={"message": "hola"}, headers={"Origin": _ORIGIN},
    )

    # El proyecto no tiene instantánea -- sigue siendo 404 (CORS no
    # cambia la lógica de negocio) pero el navegador ya puede leer esa
    # respuesta porque trae la cabecera correcta.
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == _ORIGIN
