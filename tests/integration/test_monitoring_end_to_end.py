"""Prueba de integración real de punta a punta de la Fase 5 (ADR-002,
"lazo de mejora continua"): una conversación real, atendida por
`interfaces/api/` (Fase 2, FastAPI real vía TestClient) y registrada
en `runtime.db`, se lee después con `RuntimeMonitoringService` --
mismo servicio que usaría la pestaña de Monitoreo -- y se promueve a
un caso de prueba real, persistido con `SqlAlchemyTestCaseRepository`
(el mismo repositorio que ya usa la pestaña Calidad). Ninguna de las
tres piezas es un doble."""
from __future__ import annotations

from fastapi.testclient import TestClient

from application.runtime.service import RuntimeMonitoringService
from domain.conversational.entities import Intent
from domain.documents.entities import Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk
from domain.quality.entities import TestCategory
from domain.rag.entities import VectorPoint
from domain.release.entities import ProjectSnapshot
from infrastructure.database.conversational_repositories import SqlAlchemyIntentRepository
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.quality_repositories import SqlAlchemyTestCaseRepository
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.runtime_repositories import SqlAlchemyConversationLogRepository
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from interfaces.api.app import create_app

from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

_PROJECT_ID = "p1"
_HORARIO_TEXT = "El horario de atención es de lunes a viernes de 9 a 17 horas."


def _publish_sample_project(paths):
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    source = Source(
        project_id=_PROJECT_ID, title="Horarios", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.VALIDADO,
    )
    SqlAlchemySourceRepository(paths).save(source)

    chunk = Chunk(project_id=_PROJECT_ID, source_id=source.id, chunk_index=0, text=_HORARIO_TEXT, token_count=12)
    SqlAlchemyChunkRepository(paths).save_many(_PROJECT_ID, [chunk])

    embedding_provider = WordOverlapFakeEmbeddingProvider()
    vector = embedding_provider.embed_texts([chunk.text])[0]
    vector_store = QdrantLocalVectorStore(paths)
    vector_store.ensure_collection(_PROJECT_ID, vector_size=len(vector))
    vector_store.upsert(_PROJECT_ID, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": source.id})])

    intent = Intent(
        project_id=_PROJECT_ID, name="Consultar horario",
        positive_examples=["¿cuál es el horario de atención?", "horario de atención"],
    )
    SqlAlchemyIntentRepository(paths).save(intent)

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )


def _fake_embedding_provider_factory(_profile, _cache_dir):
    return WordOverlapFakeEmbeddingProvider()


def test_a_real_conversation_can_be_read_and_promoted_by_the_desktop_app(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    _publish_sample_project(paths)

    # ---- Rol 1: interfaces/api/ (el runtime) atiende un mensaje real ----
    app = create_app(paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory)
    client = TestClient(app)
    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    assert response.status_code == 200
    log_id = response.json()["log_id"]

    # ---- Rol 2: la app de escritorio (Monitoreo) lee el mismo runtime.db ----
    log_repository = SqlAlchemyConversationLogRepository(paths.runtime_db_path())
    test_case_repository = SqlAlchemyTestCaseRepository(paths)
    monitoring_service = RuntimeMonitoringService(log_repository, test_case_repository)

    conversations = monitoring_service.list_conversations(_PROJECT_ID)
    assert len(conversations) == 1
    assert conversations[0].id == log_id
    assert conversations[0].message == "¿cuál es el horario de atención?"

    test_case = monitoring_service.promote_to_test_case(
        _PROJECT_ID, log_id, "MON-001", TestCategory.RESPUESTA_DIRECTA,
    )

    persisted = test_case_repository.list_for_project(_PROJECT_ID)
    assert len(persisted) == 1
    assert persisted[0].id == test_case.id
    assert persisted[0].query_text == "¿cuál es el horario de atención?"
    assert persisted[0].expected_source_id is not None
