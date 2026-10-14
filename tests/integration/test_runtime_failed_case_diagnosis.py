"""Ronda 93 -- reproducción real del caso `failed` sin categoría
(SOLICITUD COMPLEMENTARIA NEXOM): API real, Qdrant real, SQLite real.

Antes de la corrección: el turno que fallaba devolvía `500 Internal Server
Error` en texto plano, sin categoría, etapa ni Trace ID, y no quedaba en
runtime.db -- el consumidor solo podía mostrar "failed" con "—".
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from application.runtime.failure_diagnosis import diagnose_exception
from application.quality.commands.run_evaluation import RunEvaluation
from domain.quality.entities import EvaluationVerdict, TestCase, TestCategory
from infrastructure.database.runtime_repositories import SqlAlchemyConversationLogRepository
from interfaces.api.app import create_app
from tests.integration.test_runtime_api import _PROJECT_ID, _publish_sample_project
from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider


class _EmbeddingQueFalla(WordOverlapFakeEmbeddingProvider):
    """Falla solo para consultas que mencionan "presupuesto" (el
    calentamiento al cargar la instantánea sí funciona)."""

    def embed_query(self, text):
        if "presupuesto" in text:
            raise RuntimeError("No se pudo cargar el modelo de embeddings: sin red")
        return super().embed_query(text)


def _cliente(paths):
    app = create_app(paths.base_dir, embedding_provider_factory=lambda _p, _c: _EmbeddingQueFalla())
    return TestClient(app, raise_server_exceptions=False)


def test_caso_failed_reproducido_queda_clasificado_persistido_y_correlacionado(tmp_path):
    paths = _publish_sample_project(tmp_path)
    cliente = _cliente(paths)

    r = cliente.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el presupuesto?"},
        headers={"X-Trace-Id": "b31014f3-14aa"},
    )
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["X-Trace-Id"] == "b31014f3-14aa"
    error = r.json()["error"]
    assert error["category"] == "embedding_error"  # CA-FAIL-01/02
    assert error["stage"] == "embeddings_consulta"  # CA-FAIL-05
    assert error["message"] and error["code"]  # CA-FAIL-06
    assert error["trace_id"] == "b31014f3-14aa"  # CA-FAIL-04
    assert error["log_id"] and error["timestamp"]

    # CA-FAIL-08: persistido en runtime.db, con el mismo trace_id.
    entrada = SqlAlchemyConversationLogRepository(paths.runtime_db_path()).get_by_id(error["log_id"])
    assert entrada is not None and entrada.action == "fallo"
    assert entrada.error_category == "embedding_error" and entrada.trace_id == "b31014f3-14aa"
    assert "RuntimeError" in (entrada.error_detail or "")


def test_casos_answered_y_abstained_sin_regresion(tmp_path):  # CA-FAIL-07
    paths = _publish_sample_project(tmp_path)
    cliente = _cliente(paths)
    ok = cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"})
    assert ok.status_code == 200
    cuerpo = ok.json()
    assert cuerpo["action"] == "responder" and cuerpo["trace_id"]
    assert ok.headers["X-Trace-Id"] == cuerpo["trace_id"]
    sin_info = cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "zzz qqq"})
    assert sin_info.status_code == 200 and sin_info.json()["action"] in ("abstenerse", "aclarar", "responder")
    entradas = SqlAlchemyConversationLogRepository(paths.runtime_db_path()).list_for_project(_PROJECT_ID)
    assert all(e.error_category is None for e in entradas)


def test_repetir_la_evaluacion_identifica_la_misma_causa(tmp_path):  # CA-FAIL-09
    paths = _publish_sample_project(tmp_path)
    cliente = _cliente(paths)
    categorias = {
        cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "presupuesto 2026"}).json()["error"]["code"]
        for _ in range(2)
    }
    assert categorias == {"embedding.RuntimeError"}


def test_trace_id_invalido_se_reemplaza(tmp_path):
    paths = _publish_sample_project(tmp_path)
    r = _cliente(paths).post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "horario"},
        headers={"X-Trace-Id": "con espacios\ny saltos"},
    )
    assert r.status_code == 200 and "\n" not in r.json()["trace_id"] and " " not in r.json()["trace_id"]


def test_instantanea_inexistente_responde_404_estructurado(tmp_path):
    paths = _publish_sample_project(tmp_path)
    r = _cliente(paths).post("/projects/otro/messages", json={"message": "hola"})
    assert r.status_code == 404
    assert r.json()["error"]["category"] == "configuration_error"


def test_metricas_reportan_turnos_fallidos(tmp_path):
    paths = _publish_sample_project(tmp_path)
    cliente = _cliente(paths)
    cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "presupuesto"})
    cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"})
    resumen = SqlAlchemyConversationLogRepository(paths.runtime_db_path()).get_metrics_summary(_PROJECT_ID)
    assert resumen.failed_turns == 1 and resumen.total_turns == 2


def test_runtime_db_anterior_se_actualiza_sin_perder_datos(tmp_path):
    """Compatibilidad: un runtime.db de antes de la Ronda 93 (sin las
    columnas de diagnóstico) se abre, conserva sus filas y gana columnas."""
    db = tmp_path / "runtime.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE conversation_log (id VARCHAR PRIMARY KEY, conversation_id VARCHAR, project_id VARCHAR NOT NULL,"
        " snapshot_version INTEGER NOT NULL, message TEXT NOT NULL, matched_intent VARCHAR, confidence FLOAT,"
        " action VARCHAR NOT NULL, response_text TEXT, source_ids TEXT NOT NULL, latency_ms FLOAT,"
        " created_at DATETIME NOT NULL)"
    )
    con.execute(
        "INSERT INTO conversation_log VALUES ('l1','c1','p1',1,'hola',NULL,NULL,'responder',NULL,'[]',12.0,?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    con.commit()
    con.close()
    repo = SqlAlchemyConversationLogRepository(db)
    viejo = repo.get_by_id("l1")
    assert viejo is not None and viejo.action == "responder" and viejo.trace_id is None
    columnas = {fila[1] for fila in sqlite3.connect(db).execute("PRAGMA table_info(conversation_log)")}
    assert {"trace_id", "error_category", "error_stage", "error_code", "error_summary", "error_detail"} <= columnas


def test_calidad_interna_caso_gris_siempre_trae_causa():
    """Auditoría Ronda 93: en la pestaña Calidad, un caso cuya simulación
    lanzaba una excepción sin mensaje quedaba gris SIN causa."""
    from tests.unit.application.fakes_quality import (
        InMemoryEvaluationRunRepository,
        InMemoryTestCaseRepository,
    )

    class _Conversacional:
        def simulate(self, *args, **kwargs):
            raise KeyError()

    casos = InMemoryTestCaseRepository()
    casos.save(TestCase(project_id="p1", code="TC-1", category=TestCategory.RESPUESTA_DIRECTA, query_text="hola"))
    corrida = RunEvaluation(casos, InMemoryEvaluationRunRepository(), _Conversacional()).execute("p1")
    item = corrida.items[0]
    assert item.verdict == EvaluationVerdict.GRIS
    assert item.error and item.error.startswith("[categoría=")
    assert diagnose_exception(KeyError()).category.value == "unclassified"


def test_errores_de_la_solicitud_conservan_formato_estandar_sin_objeto_error(tmp_path):
    """Ronda 94 (auditoría de contrato): CONTRATO_INTEGRACION.md 5bis
    documenta que 401/422/429 responden {"detail": ...} sin "error"."""
    paths = _publish_sample_project(tmp_path)
    app = create_app(
        paths.base_dir, embedding_provider_factory=lambda _p, _c: _EmbeddingQueFalla(), api_key="clave",
        rate_limit_per_minute=1,
    )
    cliente = TestClient(app, raise_server_exceptions=False)
    sin_clave = cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "horario"})
    assert sin_clave.status_code == 401 and "error" not in sin_clave.json()
    invalido = cliente.post(f"/projects/{_PROJECT_ID}/messages", json={}, headers={"X-API-Key": "clave"})
    assert invalido.status_code in (422, 429) and "error" not in invalido.json()
    for _ in range(2):
        r = cliente.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "horario"}, headers={"X-API-Key": "clave"})
    assert r.status_code == 429 and "error" not in r.json()
