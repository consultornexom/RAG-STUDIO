"""Ronda 104b, Etapa 0 (autorizada por NEXOM): trazabilidad de ejecución en
el Runtime -- /messages (campo `execution`, solo con la credencial operativa),
/health (público, sin detalles internos), /health/details (protegido),
runtime.db (columnas aditivas, compatibilidad con bases anteriores) y
ningún cambio en el orden ni en los campos existentes de la respuesta."""
from __future__ import annotations

import json
import sqlite3

from infrastructure.database.runtime_repositories import SqlAlchemyConversationLogRepository

from tests.integration.test_runtime_api import _PROJECT_ID, _make_client, _publish_sample_project

_KEY = "clave-operativa-etapa0"
_PREGUNTA = {"message": "¿cuál es el horario de atención?"}
_CAMPOS_EXISTENTES = {
    "action", "response_text", "matched_intent", "confidence", "sources", "snapshot_version", "log_id",
    "conversation_id", "latency_ms", "trace_id", "missing_variables", "structured_result", "image_results",
}


def _cliente(tmp_path, **kw):
    paths = _publish_sample_project(tmp_path)
    return paths, _make_client(paths.base_dir, api_key=_KEY, **kw)


def test_messages_con_clave_operativa_trae_execution_completo(tmp_path):
    paths, client = _cliente(tmp_path)
    r = client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA,
                    headers={"X-API-Key": _KEY, "X-Trace-Id": "trace-etapa0-1"})
    assert r.status_code == 200
    body = r.json()
    assert _CAMPOS_EXISTENTES <= set(body)  # se conservan todos los campos existentes
    ejecucion = body["execution"]
    assert ejecucion["format_version"] == 1
    assert ejecucion["code"]["version"] and "fingerprint" in ejecucion["code"]
    assert ejecucion["snapshot"]["project_id"] == _PROJECT_ID and ejecucion["snapshot"]["version"] == 1
    assert ejecucion["snapshot"]["declared_fingerprint"].startswith("sha256:")
    assert ejecucion["snapshot"]["fingerprint_matches"] is True
    assert ejecucion["index"]["query_embedding_profile"] == "simetrico"
    assert ejecucion["retrieval_pipeline"] == "r105b"
    # El Runtime de RAG Studio no tiene modelo de reranking: se informa así.
    assert ejecucion["reranking"] == {
        "setting": "automatico", "model_available": False, "available_model": None,
        "model_status": "no_requerido", "effective_in_runtime": "sin_reranking",
        "applied": False, "model": None, "note": None,
    }
    assert ejecucion["search_text"] == _PREGUNTA["message"]
    assert [x["chunk_id"] for x in ejecucion["results"]] == [s["chunk_id"] for s in body["sources"]]
    assert body["sources"][0]["retrieval_rank"] == 1
    serializado = json.dumps(ejecucion)
    assert _KEY not in serializado and str(paths.base_dir) not in serializado  # ni secretos ni rutas


def test_messages_con_token_de_widget_no_expone_execution(tmp_path):
    _, client = _cliente(tmp_path)
    token = client.post(f"/projects/{_PROJECT_ID}/widget-tokens", json={"max_access_level": "confidencial"},
                        headers={"X-API-Key": _KEY}).json()["token"]
    body = client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA,
                       headers={"X-Widget-Token": token}).json()
    assert body["action"] == "responder"
    assert body["execution"] is None
    assert body["sources"][0]["retrieval_rank"] is None and body["sources"][0]["affinity"] is None


def test_el_orden_de_fragmentos_no_cambia_con_o_sin_execution(tmp_path):
    _, client = _cliente(tmp_path)
    token = client.post(f"/projects/{_PROJECT_ID}/widget-tokens", json={"max_access_level": "confidencial"},
                        headers={"X-API-Key": _KEY}).json()["token"]
    a = client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA, headers={"X-API-Key": _KEY}).json()
    b = client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA, headers={"X-Widget-Token": token}).json()
    assert [(s["chunk_id"], s["score"]) for s in a["sources"]] == [(s["chunk_id"], s["score"]) for s in b["sources"]]


def test_runtime_db_guarda_orden_y_ejecucion_localizables_por_trace(tmp_path):
    paths, client = _cliente(tmp_path)
    body = client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA,
                       headers={"X-API-Key": _KEY, "X-Trace-Id": "trace-etapa0-db"}).json()
    con = sqlite3.connect(paths.runtime_db_path())
    chunk_ids, ejecucion = con.execute(
        "select chunk_ids, execution from conversation_log where trace_id='trace-etapa0-db'").fetchone()
    assert json.loads(chunk_ids) == [s["chunk_id"] for s in body["sources"]]
    guardado = json.loads(ejecucion)
    assert guardado["snapshot"]["declared_fingerprint"] == body["execution"]["snapshot"]["declared_fingerprint"]
    assert guardado["code"]["fingerprint"] == body["execution"]["code"]["fingerprint"]
    assert _KEY not in ejecucion


def test_health_publico_sin_detalles_internos_y_details_protegido(tmp_path):
    _, client = _cliente(tmp_path)
    publico = client.get("/health").json()
    assert publico["retrieval_pipeline"] == "r105b" and publico["code_version"]
    assert "commit" not in json.dumps(publico) and "fingerprint" not in json.dumps(publico)
    assert client.get("/health/details").status_code == 401
    client.post(f"/projects/{_PROJECT_ID}/messages", json=_PREGUNTA, headers={"X-API-Key": _KEY})
    detalles = client.get("/health/details", headers={"X-API-Key": _KEY}).json()
    assert detalles["code"]["fingerprint"] and detalles["retrieval_pipeline"] == "r105b"
    assert detalles["reranking_model_available"] is False
    assert detalles["loaded_snapshots"][0]["snapshot"]["version"] == 1
    assert set(detalles["package_fingerprints"]) >= {"application", "domain", "infrastructure", "interfaces"}


def test_runtime_db_anterior_sin_columnas_nuevas_conserva_sus_filas(tmp_path):
    db = tmp_path / "runtime.db"
    con = sqlite3.connect(db)
    # Esquema de conversation_log anterior a la Ronda 19 (sin conversation_id
    # ni columnas de diagnóstico ni de ejecución).
    con.execute("""create table conversation_log (id varchar primary key, project_id varchar not null,
        snapshot_version integer not null, message text not null, matched_intent varchar, confidence float,
        action varchar not null, response_text text, source_ids text not null, latency_ms float,
        created_at datetime not null)""")
    con.execute("insert into conversation_log values ('fila-vieja','p1',1,'hola',null,null,'abstenerse',null,"
                "'[\"s1\"]',1.0,'2026-01-01 00:00:00.000000')")
    con.commit()
    con.close()
    repo = SqlAlchemyConversationLogRepository(db)
    [vieja] = repo.list_for_project("p1")
    assert vieja.id == "fila-vieja" and vieja.source_ids == ["s1"]
    assert vieja.chunk_ids is None and vieja.execution is None
    columnas = {r[1] for r in sqlite3.connect(db).execute("pragma table_info(conversation_log)")}
    assert {"chunk_ids", "execution", "trace_id", "conversation_id"} <= columnas
