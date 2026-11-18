"""Ronda 104b, Etapa 0: registro de ejecución de un turno."""
from domain.conversational.entities import RuleActionType
from domain.ingestion.entities import Chunk

from application.conversational.queries.simulate_conversation import ResultOrderingView, SimulationTrace
from application.rag.queries.semantic_search import SemanticSearchResult
from application.runtime.execution_info import execution_record, failure_execution_record

BASE = {
    "code": {"version": "0.1.0", "commit": None, "unknown": ["commit", "dirty"], "fingerprint": "f"},
    "snapshot": {"project_id": "p", "version": 2, "declared_fingerprint": None, "fingerprint_at_load": "sha256:x"},
    "index": {"embedding_model": "m"},
}


def _r(cid, sid="s"):
    return SemanticSearchResult(chunk=Chunk(id=cid, project_id="p", source_id=sid, chunk_index=0, text="t",
                                            token_count=1), score=0.5)


def test_registro_con_reordenamiento_conserva_orden_y_puestos():
    trace = SimulationTrace(
        query_text="q", action=RuleActionType.RESPONDER, search_results=[_r("b"), _r("a")],
        result_ordering=[ResultOrderingView(retrieval_rank=3, affinity=0.4, affinity_title="T"),
                         ResultOrderingView(retrieval_rank=1, affinity=0.0, affinity_title="")],
        applied_metadata_filters={"nivel": "bachillerato"}, search_text="q sin valor", reranking_setting="automatico",
    )
    reg = execution_record(BASE, trace)
    assert [(x["position"], x["chunk_id"], x["retrieval_rank"], x["affinity"]) for x in reg["results"]] == [
        (1, "b", 3, 0.4), (2, "a", 1, 0.0)]
    assert reg["search_text"] == "q sin valor" and reg["applied_filters"] == {"nivel": "bachillerato"}
    assert reg["retrieval_pipeline"] == "r105b"
    assert reg["reranking"]["applied"] is False and reg["reranking"]["model_available"] is False
    assert set(reg["unknown"]) == {"code.commit", "code.dirty", "snapshot.declared_fingerprint"}


def test_sin_reordenamiento_el_puesto_es_la_posicion_y_sin_base_todo_es_desconocido():
    trace = SimulationTrace(query_text="q", action=RuleActionType.RESPONDER, search_results=[_r("a"), _r("b")])
    reg = execution_record(None, trace)
    assert [x["retrieval_rank"] for x in reg["results"]] == [1, 2]
    assert [x["affinity"] for x in reg["results"]] == [None, None]
    assert set(reg["unknown"]) == {"code", "snapshot", "index"}


def test_turno_fallido_solo_lleva_la_parte_fija():
    reg = failure_execution_record(BASE)
    assert reg["code"] == BASE["code"] and "results" not in reg
