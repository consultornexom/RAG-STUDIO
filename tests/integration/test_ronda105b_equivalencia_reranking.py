"""Ronda 105b (P1, alternativa B estricta, decisión de NEXOM): equivalencia
entre el Simulador (app de escritorio) y el Runtime (POST /messages) con la
MISMA instantánea, el mismo ajuste de reranking y las mismas consultas.

- Escritorio: ConversationalService sobre el proyecto de la instalación,
  con modelo de reranking disponible (como la app real).
- Runtime: create_app sobre la instantánea publicada de ese mismo proyecto.

Casos: Automático, Desactivado, Activado con modelo (ambos aplican el
reranking) y Activado sin modelo (ambos fallan de forma explícita)."""
from __future__ import annotations

import pytest

from application.conversational.service import ConversationalService
from application.rag.service import RagService
from domain.conversational.entities import Intent
from domain.documents.entities import Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk
from domain.projects.entities import Project
from domain.rag.entities import VectorPoint
from domain.rag.exceptions import RerankerError, RerankingRequiredUnavailableError
from domain.release.entities import ProjectSnapshot
from fastapi.testclient import TestClient
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository, SqlAlchemyConversationalVariableRepository,
    SqlAlchemyGuardrailRuleRepository, SqlAlchemyIntentRepository,
)
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.metadata_repositories import (
    SqlAlchemyCatalogRepository, SqlAlchemyMetadataSchemaRepository, SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.repositories import ProjectAgentRerankingReader, SqlAlchemyProjectRepository
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from interfaces.api.app import create_app

from tests.unit.application.fakes_rag import FakeReranker, WordOverlapFakeEmbeddingProvider

P = "p-eq"
KEY = "clave-eq"
TEXTOS = [
    "horario de atención general de la oficina",
    "horario de atención de admisiones relevante para aspirantes",
    "horario de la biblioteca y atención en ventanilla",
]
CONSULTAS = ["¿cuál es el horario de atención?", "horario de atención de admisiones", "horario de la biblioteca"]


class RerankerQueNoCarga(FakeReranker):
    def ensure_ready(self):
        raise RerankerError("modelo no aprovisionado en este servidor")

    @property
    def is_loaded(self):
        return False


def _instalacion(tmp_path, ajuste, embedder):
    """`embedder` se comparte entre la indexación, el escritorio y el Runtime:
    WordOverlapFakeEmbeddingProvider asigna posiciones por instancia."""
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(P)
    SqlAlchemyProjectRepository(paths).save(Project(id=P, name="Equivalencia", agent_reranking=ajuste))
    fuente = Source(project_id=P, title="Horarios", source_type=SourceType.TXT,
                    validation_status=SourceValidationStatus.VALIDADO)
    SqlAlchemySourceRepository(paths).save(fuente)
    chunks = [Chunk(project_id=P, source_id=fuente.id, chunk_index=i, text=t, token_count=len(t.split()))
              for i, t in enumerate(TEXTOS)]
    SqlAlchemyChunkRepository(paths).save_many(P, chunks)
    store = QdrantLocalVectorStore(paths)
    vectores = embedder.embed_texts(TEXTOS)
    store.ensure_collection(P, vector_size=len(vectores[0]))
    store.upsert(P, [VectorPoint(id=c.id, vector=v, payload={"source_id": fuente.id})
                     for c, v in zip(chunks, vectores, strict=True)])
    SqlAlchemyIntentRepository(paths).save(Intent(
        project_id=P, name="Consultar horario", positive_examples=["¿cuál es el horario de atención?", "horario"],
    ))
    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(P, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(ProjectSnapshot(project_id=P, version=1, snapshot_dir=snapshot_dir))
    return paths


def _simulador_escritorio(paths, reranker, embedder):
    """Mismo armado que app/bootstrap.py, sobre el proyecto de la instalación."""
    rag = RagService(SqlAlchemyChunkRepository(paths), embedder,
                     QdrantLocalVectorStore(paths), SqlAlchemyIndexInfoRepository(paths),
                     source_repository=SqlAlchemySourceRepository(paths), reranker=reranker)
    return ConversationalService(
        SqlAlchemyIntentRepository(paths), SqlAlchemyConversationalVariableRepository(paths),
        SqlAlchemyGuardrailRuleRepository(paths), SqlAlchemyChannelingSchemeRepository(paths),
        SqlAlchemySourceMetadataRepository(paths), rag, source_repository=SqlAlchemySourceRepository(paths),
        schema_repository=SqlAlchemyMetadataSchemaRepository(paths), catalog_repository=SqlAlchemyCatalogRepository(paths),
        agent_reranking=ProjectAgentRerankingReader(paths),
    )


def _runtime(paths, reranker_factory, embedder):
    return TestClient(create_app(
        paths.base_dir, api_key=KEY, embedding_provider_factory=lambda _p, _c: embedder,
        reranker_factory=reranker_factory,
    ))


@pytest.mark.parametrize("ajuste, aplicado", [(None, False), (False, False), (True, True)])
def test_simulador_y_runtime_dan_el_mismo_resultado_con_la_misma_configuracion(tmp_path, ajuste, aplicado):
    embedder = WordOverlapFakeEmbeddingProvider()
    paths = _instalacion(tmp_path, ajuste, embedder)
    escritorio = _simulador_escritorio(paths, FakeReranker("modelo-x"), embedder)
    cliente = _runtime(paths, lambda _dir: FakeReranker("modelo-x"), embedder)
    for consulta in CONSULTAS:
        traza = escritorio.simulate(P, consulta)
        cuerpo = cliente.post(f"/projects/{P}/messages", json={"message": consulta},
                              headers={"X-API-Key": KEY}).json()
        assert [r.chunk.id for r in traza.search_results] == [s["chunk_id"] for s in cuerpo["sources"]], consulta
        assert [round(r.score, 9) for r in traza.search_results] == [round(s["score"], 9) for s in cuerpo["sources"]]
        assert traza.action.value == cuerpo["action"]
        rer = cuerpo["execution"]["reranking"]
        assert traza.reranking_applied is aplicado and rer["applied"] is aplicado
        assert traza.runtime_effective_reranking == rer["effective_in_runtime"] == (
            "con_reranking" if aplicado else "sin_reranking")
        assert rer["model_status"] == ("cargado" if aplicado else "no_requerido")
        assert cuerpo["execution"]["retrieval_pipeline"] == traza.retrieval_pipeline == "r105b"


def test_automatico_en_el_runtime_no_construye_ni_requiere_modelo(tmp_path):
    """Condición 7: sin «Activado», el Runtime no necesita modelo de reranking."""
    embedder = WordOverlapFakeEmbeddingProvider()
    paths = _instalacion(tmp_path, None, embedder)

    def prohibido(_dir):
        raise AssertionError("el Runtime no debe construir un reranker sin «Activado»")

    cuerpo = _runtime(paths, prohibido, embedder).post(f"/projects/{P}/messages", json={"message": CONSULTAS[0]},
                                             headers={"X-API-Key": KEY}).json()
    assert cuerpo["action"] == "responder"
    assert cuerpo["execution"]["reranking"]["model_available"] is False


def test_activado_sin_modelo_falla_explicito_en_simulador_y_runtime(tmp_path):
    embedder = WordOverlapFakeEmbeddingProvider()
    paths = _instalacion(tmp_path, True, embedder)
    with pytest.raises(RerankingRequiredUnavailableError):
        _simulador_escritorio(paths, RerankerQueNoCarga("modelo-x"), embedder).simulate(P, CONSULTAS[0])
    with pytest.raises(RerankingRequiredUnavailableError):
        _simulador_escritorio(paths, None, embedder).simulate(P, CONSULTAS[0])
    respuesta = _runtime(paths, lambda _dir: RerankerQueNoCarga("modelo-x"), embedder).post(
        f"/projects/{P}/messages", json={"message": CONSULTAS[0]}, headers={"X-API-Key": KEY})
    assert respuesta.status_code == 503
    error = respuesta.json()["error"]
    assert error["code"] == "configuration.reranking_unavailable"
    assert error["category"] == "configuration_error"
    assert "Activado" in respuesta.json()["detail"]
