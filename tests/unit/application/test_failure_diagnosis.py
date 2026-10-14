"""Ronda 93 (SOLICITUD COMPLEMENTARIA NEXOM, caso `failed` con
"Categoría de error = —"): clasificación determinista de fallos y
registro del turno fallido."""
from __future__ import annotations

import sqlite3
import types

import pytest

from application.runtime.commands.handle_incoming_message import (
    HandleIncomingMessage,
    MessageHandlingFailedError,
)
from application.runtime.failure_diagnosis import diagnose_exception, format_evaluation_error
from domain.runtime.entities import FAILED_ACTION, ConversationLogEntry
from domain.runtime.failures import FailureCategory, FailureStage

from .fakes_runtime import InMemoryConversationLogRepository


def _lanzar_desde(nombre_modulo: str, funcion: str, exc: BaseException) -> BaseException:
    """Lanza `exc` desde una función definida en un módulo con ese nombre
    (simula la cadena de llamadas real sin depender de modelos/índices).
    El módulo NO se registra en sys.modules: solo importa el `__name__`
    que ve el marco de la traza."""
    modulo = types.ModuleType(nombre_modulo)
    codigo = f"def {funcion}(exc):\n    raise exc\n"
    exec(compile(codigo, nombre_modulo, "exec"), modulo.__dict__)  # noqa: S102 - solo pruebas
    try:
        getattr(modulo, funcion)(exc)
    except BaseException as capturada:  # noqa: BLE001
        return capturada
    raise AssertionError("no lanzó")


@pytest.mark.parametrize(("modulo", "funcion", "categoria", "etapa"), [
    ("infrastructure.embeddings.fastembed_provider", "embed_query", FailureCategory.EMBEDDING,
     FailureStage.EMBEDDINGS_CONSULTA),
    ("infrastructure.vectorstores.qdrant_local_store", "search", FailureCategory.RETRIEVAL, FailureStage.BUSQUEDA),
    ("domain.conversational.rule_evaluation", "evaluate", FailureCategory.GUARDRAIL, FailureStage.GUARDRAILS),
    ("domain.conversational.intent_matching", "match_intent", FailureCategory.INTENT,
     FailureStage.DETECCION_INTENCION),
    ("infrastructure.database.metadata_repositories", "list_for_source", FailureCategory.SOURCE,
     FailureStage.FILTRADO_METADATOS),
])
def test_categoria_y_etapa_salen_del_componente_real(modulo, funcion, categoria, etapa):
    diagnostico = diagnose_exception(_lanzar_desde(modulo, funcion, RuntimeError("falla")))
    assert diagnostico.category == categoria
    assert diagnostico.stage == etapa
    assert diagnostico.summary and diagnostico.code and diagnostico.technical_detail
    assert modulo in diagnostico.technical_detail


def test_tipos_inequivocos_tienen_prioridad():
    assert diagnose_exception(_lanzar_desde("x.a", "f", TimeoutError())).category == FailureCategory.TIMEOUT
    bloqueo = _lanzar_desde("x.b", "f", sqlite3.OperationalError("database is locked"))
    d = diagnose_exception(bloqueo)
    assert d.category == FailureCategory.STORAGE and d.code == "storage.database_locked"


def test_excepcion_sin_mensaje_nunca_deja_categoria_ni_resumen_vacios():
    d = diagnose_exception(_lanzar_desde("modulo.desconocido", "f", KeyError()))
    assert d.category == FailureCategory.UNEXPECTED
    assert d.summary and "KeyError" in d.summary
    sin_traza = diagnose_exception(ValueError("x"))
    assert sin_traza.category == FailureCategory.UNCLASSIFIED


def test_causa_encadenada_se_clasifica_por_la_raiz():
    raiz = _lanzar_desde("infrastructure.embeddings.fastembed_provider", "embed_query", OSError("sin red"))
    try:
        raise RuntimeError("no se pudo calcular el vector") from raiz
    except RuntimeError as exterior:
        d = diagnose_exception(exterior)
    assert d.category == FailureCategory.EMBEDDING
    assert "OSError" in (d.technical_detail or "")


def test_diagnostico_es_determinista():
    exc = _lanzar_desde("infrastructure.vectorstores.qdrant_local_store", "search", RuntimeError("x"))
    assert diagnose_exception(exc) == diagnose_exception(exc)


def test_error_de_evaluacion_nunca_vacio():
    texto = format_evaluation_error(diagnose_exception(_lanzar_desde("m.x", "f", AssertionError())))
    assert texto.startswith("[categoría=unexpected_exception")


# ---------------------------------------------------------------- caso de uso

class _Falla:
    def simulate(self, *args, **kwargs):
        raise _lanzar_desde("infrastructure.embeddings.fastembed_provider", "embed_query", RuntimeError("sin red"))


def test_turno_fallido_se_persiste_con_diagnostico_y_trace_id():
    repo = InMemoryConversationLogRepository()
    with pytest.raises(MessageHandlingFailedError) as exc:
        HandleIncomingMessage(_Falla(), repo).execute("p1", 2, "¿hola?", trace_id="caso-57c769e4")
    entradas = repo.list_for_project("p1")
    assert len(entradas) == 1
    e = entradas[0]
    assert e.action == FAILED_ACTION and e.failed
    assert e.error_category == "embedding_error" and e.error_stage == "embeddings_consulta"
    assert e.trace_id == "caso-57c769e4" and e.error_summary and e.error_detail
    assert exc.value.log_entry is not None and exc.value.log_entry.id == e.id


def test_si_runtime_db_falla_el_diagnostico_igual_se_entrega():
    class _RepoRoto(InMemoryConversationLogRepository):
        def save(self, entry: ConversationLogEntry) -> None:
            raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(MessageHandlingFailedError) as exc:
        HandleIncomingMessage(_Falla(), _RepoRoto()).execute("p1", 2, "¿hola?")
    assert exc.value.log_entry is None
    assert exc.value.diagnosis.category == FailureCategory.EMBEDDING


def test_metricas_excluyen_fallos_de_abstencion_y_latencia():
    repo = InMemoryConversationLogRepository()
    repo.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="a", action="abstenerse",
                                   latency_ms=100))
    repo.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="b", action="responder",
                                   latency_ms=300))
    repo.save(ConversationLogEntry(project_id="p1", snapshot_version=1, message="c", action=FAILED_ACTION,
                                   latency_ms=9000, error_category="embedding_error"))
    resumen = repo.get_metrics_summary("p1")
    assert resumen.total_turns == 3 and resumen.failed_turns == 1
    assert resumen.abstention_rate == 0.5
    assert resumen.avg_latency_ms == 200
    assert resumen.failure_rate == pytest.approx(1 / 3)
