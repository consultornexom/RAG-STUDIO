"""Ronda 12/13 (ver Validacion_observaciones_RAG_STUDIO.md): cierra el
punto de deuda técnica señalado desde la auditoría de la Ronda 10--
sin desalojo, `RuntimeContext._loaded` crecía sin límite en un proceso
de larga duración al que se le publicaran instantáneas nuevas del
mismo proyecto una y otra vez, porque `get_latest` nunca vuelve a
consultar una versión superada.

Prueba de integración real (SQLite/Qdrant reales, no dobles para la
publicación de instantáneas ni para el registro de versiones) contra
`RuntimeContext` directamente -- sin pasar por `create_app`/`TestClient`,
para poder inspeccionar `loaded_project_ids()` sin que el resto de la
API HTTP sea relevante para lo que se está probando aquí."""
from __future__ import annotations

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
from interfaces.api.runtime_context import RuntimeContext

from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

_HORARIO_TEXT = "El horario de atención es de lunes a viernes de 9 a 17 horas."


def _fake_embedding_provider_factory(_profile, _cache_dir):
    return WordOverlapFakeEmbeddingProvider()


def _publish_version(paths: InstallationPaths, project_id: str, version: int) -> None:
    """Publica una versión nueva de `project_id` -- si es la primera
    vez que se ve ese proyecto, primero le crea el contenido mínimo
    para que el runtime pueda calentarse sobre él (fuente, chunk,
    índice Qdrant, intención); versiones siguientes solo publican una
    copia nueva del mismo contenido, que es todo lo que esta prueba
    necesita: no le importa que el contenido cambie entre versiones,
    solo que cada una sea una instantánea real, propia, en disco."""
    project_dir_exists = paths.project_dir(project_id).exists()
    if not project_dir_exists:
        paths.ensure_project_layout(project_id)
        source = Source(
            project_id=project_id, title="Horarios", source_type=SourceType.TXT,
            validation_status=SourceValidationStatus.VALIDADO,
        )
        SqlAlchemySourceRepository(paths).save(source)
        chunk = Chunk(project_id=project_id, source_id=source.id, chunk_index=0, text=_HORARIO_TEXT, token_count=12)
        SqlAlchemyChunkRepository(paths).save_many(project_id, [chunk])
        embedding_provider = WordOverlapFakeEmbeddingProvider()
        vector = embedding_provider.embed_texts([chunk.text])[0]
        vector_store = QdrantLocalVectorStore(paths)
        vector_store.ensure_collection(project_id, vector_size=len(vector))
        vector_store.upsert(project_id, [
            VectorPoint(id=chunk.id, vector=vector, payload={"source_id": source.id}),
        ])
        intent = Intent(
            project_id=project_id, name="Consultar horario",
            positive_examples=["¿cuál es el horario de atención?", "horario de atención"],
        )
        SqlAlchemyIntentRepository(paths).save(intent)

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(project_id, version)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=project_id, version=version, snapshot_dir=snapshot_dir),
    )


def test_loading_a_new_version_evicts_the_previous_version_of_the_same_project(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    _publish_version(paths, "p1", 1)

    runtime_context = RuntimeContext(paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory)
    runtime_context.get_latest("p1")
    assert runtime_context.loaded_project_ids() == ["p1:1"]

    _publish_version(paths, "p1", 2)
    runtime_context.get_latest("p1")

    # p1:1 debe haber sido desalojada -- get_latest ya nunca la va a
    # volver a pedir, así que no tiene sentido seguir pagando su
    # memoria (incluido el proveedor de embeddings calentado para ella).
    assert runtime_context.loaded_project_ids() == ["p1:2"]


def test_evicting_a_project_does_not_touch_other_projects_cached_versions(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    _publish_version(paths, "p1", 1)
    _publish_version(paths, "p2", 1)

    runtime_context = RuntimeContext(paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory)
    runtime_context.get_latest("p1")
    runtime_context.get_latest("p2")
    assert runtime_context.loaded_project_ids() == ["p1:1", "p2:1"]

    _publish_version(paths, "p1", 2)
    runtime_context.get_latest("p1")

    # Se desaloja SOLO la versión superada de p1 -- p2 (un proyecto
    # sin relación) sigue en caché exactamente como estaba.
    assert runtime_context.loaded_project_ids() == ["p1:2", "p2:1"]


def test_a_pinned_snapshot_never_accumulates_more_than_one_cached_entry(tmp_path):
    """Modo de despliegue con RAGSTUDIO_SNAPSHOT_DIR fijo (Ronda 10,
    hallazgos A3/B1): siempre resuelve la MISMA versión configurada, así
    que nunca había un problema de acumulación en este modo -- se
    confirma aquí para que quede explícito, no solo inferido."""
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    _publish_version(paths, "p1", 1)
    snapshot_dir = paths.snapshot_version_dir("p1", 1)

    runtime_context = RuntimeContext(
        paths.base_dir, embedding_provider_factory=_fake_embedding_provider_factory,
        pinned_snapshot_dir=snapshot_dir, pinned_snapshot_version=1,
    )
    for _ in range(3):
        runtime_context.get_latest("p1")

    assert runtime_context.loaded_project_ids() == ["p1:1"]
