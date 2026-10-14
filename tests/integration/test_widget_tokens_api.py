"""Prueba de integración real del token de widget por proyecto
(ADR-002, Fase 4) -- emitir, listar, revocar y usarlo para autenticar
`POST /projects/{id}/messages`, contra `TestClient` real (no dobles de
la capa HTTP)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from infrastructure.filesystem.paths import InstallationPaths
from interfaces.api.app import create_app

_API_KEY = "secreto-admin"


def _make_client(tmp_path, **kwargs) -> TestClient:
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    app = create_app(paths.base_dir, api_key=_API_KEY, **kwargs)
    return TestClient(app)


def _admin_headers():
    return {"X-API-Key": _API_KEY}


def test_issuing_a_widget_token_requires_the_global_api_key(tmp_path):
    client = _make_client(tmp_path)

    unauthorized = client.post("/projects/p1/widget-tokens")
    assert unauthorized.status_code == 401

    authorized = client.post("/projects/p1/widget-tokens", headers=_admin_headers())
    assert authorized.status_code == 200
    body = authorized.json()
    assert body["project_id"] == "p1"
    assert body["token"]


def test_a_widget_token_authenticates_messages_for_its_own_project_only(tmp_path):
    client = _make_client(tmp_path)
    token = client.post("/projects/p1/widget-tokens", headers=_admin_headers()).json()["token"]

    own_project = client.post(
        "/projects/p1/messages", json={"message": "hola"}, headers={"X-Widget-Token": token},
    )
    other_project = client.post(
        "/projects/otro-proyecto/messages", json={"message": "hola"}, headers={"X-Widget-Token": token},
    )

    # Ninguno de los dos proyectos tiene instantánea publicada -- lo
    # que importa aquí es que "p1" pasa la autenticación (404 por
    # falta de instantánea, no 401), mientras "otro-proyecto" ni
    # siquiera llega a esa validación (401, el token no le pertenece).
    assert own_project.status_code == 404
    assert other_project.status_code == 401


def test_a_revoked_widget_token_no_longer_authenticates(tmp_path):
    client = _make_client(tmp_path)
    issued = client.post("/projects/p1/widget-tokens", headers=_admin_headers()).json()
    token, token_id = issued["token"], issued["id"]

    still_valid = client.post("/projects/p1/messages", json={"message": "hola"}, headers={"X-Widget-Token": token})
    assert still_valid.status_code == 404  # pasa la autenticación, falla después por falta de instantánea.

    revoke_response = client.delete(f"/projects/p1/widget-tokens/{token_id}", headers=_admin_headers())
    assert revoke_response.status_code == 204

    after_revoke = client.post("/projects/p1/messages", json={"message": "hola"}, headers={"X-Widget-Token": token})
    assert after_revoke.status_code == 401


def test_listing_widget_tokens_never_exposes_the_raw_token_value(tmp_path):
    client = _make_client(tmp_path)
    client.post("/projects/p1/widget-tokens", headers=_admin_headers())

    response = client.get("/projects/p1/widget-tokens", headers=_admin_headers())

    assert response.status_code == 200
    tokens = response.json()
    assert len(tokens) == 1
    assert "token" not in tokens[0]
    assert tokens[0]["is_active"] is True


def test_listing_and_revoking_widget_tokens_requires_the_global_api_key(tmp_path):
    client = _make_client(tmp_path)
    issued = client.post("/projects/p1/widget-tokens", headers=_admin_headers()).json()

    unauthorized_list = client.get("/projects/p1/widget-tokens")
    unauthorized_delete = client.delete(f"/projects/p1/widget-tokens/{issued['id']}")

    assert unauthorized_list.status_code == 401
    assert unauthorized_delete.status_code == 401


def test_revoking_an_unknown_token_id_returns_404(tmp_path):
    client = _make_client(tmp_path)

    response = client.delete("/projects/p1/widget-tokens/no-existe", headers=_admin_headers())

    assert response.status_code == 404


def test_revoking_a_token_from_a_different_project_returns_404(tmp_path):
    client = _make_client(tmp_path)
    issued = client.post("/projects/p1/widget-tokens", headers=_admin_headers()).json()

    response = client.delete(f"/projects/otro-proyecto/widget-tokens/{issued['id']}", headers=_admin_headers())

    assert response.status_code == 404


def test_the_global_api_key_still_authenticates_messages_directly(tmp_path):
    # No debe romperse el comportamiento de la Fase 2/3 -- la API key
    # global sigue funcionando exactamente igual, sin ningún token de
    # widget de por medio.
    client = _make_client(tmp_path)

    response = client.post("/projects/p1/messages", json={"message": "hola"}, headers=_admin_headers())

    assert response.status_code == 404  # sin instantánea publicada, pero pasó la autenticación.
