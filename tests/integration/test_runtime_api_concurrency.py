"""Prueba de integración real del hallazgo A2 de la auditoría Ronda 10:
dos (o más) visitantes que envían un mensaje a la MISMA instantánea al
mismo tiempo no deben chocar contra el lock exclusivo que
`QdrantClient(path=...)` toma por apertura de archivo (no por
proceso) -- antes de la corrección, la segunda solicitud concurrente
fallaba con un 500 (`RuntimeError: Storage folder ... is already
accessed by another instance of Qdrant client`).

No usa ningún doble para Qdrant (`QdrantLocalVectorStore` real, sobre
un índice real en disco) ni para la concurrencia (hilos de Python
reales golpeando la misma instancia de `TestClient`, no una
simulación) -- es exactamente el escenario que se le escapó a la
batería de pruebas original, que siempre hizo solicitudes secuenciales."""
from __future__ import annotations

import queue
import threading

from fastapi.testclient import TestClient

from domain.conversational.entities import Intent
from domain.documents.entities import Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk
from domain.rag.entities import VectorPoint
from domain.release.entities import ProjectSnapshot
from infrastructure.database.conversational_repositories import SqlAlchemyIntentRepository
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from interfaces.api.app import create_app

from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

_PROJECT_ID = "p1"
_HORARIO_TEXT = "El horario de atención es de lunes a viernes de 9 a 17 horas."
_CONCURRENT_REQUESTS = 8


def _publish_sample_project(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
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
    vector_store.upsert(_PROJECT_ID, [
        VectorPoint(id=chunk.id, vector=vector, payload={"source_id": source.id}),
    ])

    intent = Intent(
        project_id=_PROJECT_ID, name="Consultar horario",
        positive_examples=["¿cuál es el horario de atención?", "horario de atención"],
    )
    SqlAlchemyIntentRepository(paths).save(intent)

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )
    return paths


def _fake_embedding_provider_factory(_profile, _cache_dir):
    return WordOverlapFakeEmbeddingProvider()


def test_concurrent_messages_against_the_same_snapshot_do_not_500(tmp_path):
    paths = _publish_sample_project(tmp_path)
    app = create_app(paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory)
    client = TestClient(app)

    # Calentar la instantánea fuera de los hilos medidos, para que la
    # carrera sea de verdad sobre las aperturas de Qdrant en `search`
    # (dentro de loaded.lock), no sobre la construcción inicial
    # (protegida por RuntimeContext._lock, sin relación con este hallazgo).
    warmup = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "horario de atención"})
    assert warmup.status_code == 200

    results: "queue.Queue[tuple[int, str]]" = queue.Queue()

    def _send():
        response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "horario de atención"})
        results.put((response.status_code, response.text))

    threads = [threading.Thread(target=_send) for _ in range(_CONCURRENT_REQUESTS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    statuses = []
    while not results.empty():
        statuses.append(results.get())

    assert len(statuses) == _CONCURRENT_REQUESTS
    failed = [(status, body) for status, body in statuses if status != 200]
    assert not failed, f"solicitudes concurrentes contra la misma instantánea fallaron: {failed!r}"
