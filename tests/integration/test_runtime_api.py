"""Prueba de integración real de la API mínima del runtime (ADR-002,
Fase 2) -- construye un proyecto real (una fuente validada, un
fragmento indexado en Qdrant real, una intención), lo publica como
instantánea reutilizando `FilesystemProjectSnapshotPublisher` (Fase
1), y golpea la API real a través de `TestClient`.

Usa `WordOverlapFakeEmbeddingProvider` (no el fastembed real, que
descargaría un modelo de cientos de MB) inyectado vía
`embedding_provider_factory` -- mismo mecanismo de sustitución que ya
usa el resto de la suite para `RagService`."""
from __future__ import annotations

from fastapi.testclient import TestClient

from domain.conversational.entities import Intent, IntentResolutionMode
from domain.documents.entities import AccessLevel, Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk, ChunkType
from domain.projects.entities import Project
from domain.quality.entities import EvaluationResultItem, EvaluationRun, EvaluationVerdict, TestCategory
from domain.rag.entities import VectorPoint
from domain.release.entities import ProjectSnapshot
from infrastructure.database.conversational_repositories import SqlAlchemyIntentRepository
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.quality_repositories import SqlAlchemyEvaluationRunRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.database.runtime_repositories import (
    SqlAlchemyConversationLogRepository,
    SqlAlchemyRetrievalFeedbackRepository,
)
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from interfaces.api.app import create_app

from application.rag.service import RagService
from tests.unit.application.fakes_rag import FakeImageEmbeddingProvider, WordOverlapFakeEmbeddingProvider

_PROJECT_ID = "p1"
_HORARIO_TEXT = "El horario de atención es de lunes a viernes de 9 a 17 horas."


def _publish_sample_project(tmp_path, *, required_variables=None, access_level=None):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    source_kwargs = {} if access_level is None else {"access_level": access_level}
    source = Source(
        project_id=_PROJECT_ID, title="Horarios", source_type=SourceType.TXT,
        validation_status=SourceValidationStatus.VALIDADO, **source_kwargs,
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
        required_variables=required_variables or [],
        clarifying_questions={v: f"¿Podrías indicar '{v}'?" for v in (required_variables or [])},
    )
    SqlAlchemyIntentRepository(paths).save(intent)

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )
    return paths


def _fake_embedding_provider_factory(_profile, _cache_dir):
    return WordOverlapFakeEmbeddingProvider()


def _make_client(installation_dir, **kwargs) -> TestClient:
    app = create_app(
        installation_dir, embedding_provider_factory=_fake_embedding_provider_factory, **kwargs,
    )
    return TestClient(app)


def test_health_endpoint_reports_ok(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_post_message_answers_from_the_published_snapshot(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "responder"
    assert body["matched_intent"] == "Consultar horario"
    assert body["response_text"] is None  # sin paso de generación de lenguaje natural, ver módulo de la Fase 2
    assert len(body["sources"]) == 1
    assert body["sources"][0]["text"] == _HORARIO_TEXT
    # Pista C.5 del ADR-003 (roadmap RAG 5, Ronda 43/44): page_start/
    # page_end viajan como None para una fuente TXT (sin páginas), no
    # como 0 ni ausentes del payload.
    assert body["sources"][0]["page_start"] is None
    assert body["sources"][0]["page_end"] is None
    # Ronda 58: section_title también viaja como None para un chunk sin
    # encabezado de origen, no como cadena vacía ni ausente del payload.
    assert body["sources"][0]["section_title"] is None
    assert body["snapshot_version"] == 1
    assert body["log_id"]
    assert body["latency_ms"] >= 0


def test_post_message_includes_the_page_numbers_of_a_pdf_derived_chunk(tmp_path):
    # Pista C.5 del ADR-003 (roadmap RAG 5, Ronda 43/44): Chunk.page_start/
    # page_end ya existían desde antes de la Pista C (poblados por
    # application/ingestion/commands/fragment_source.py para fuentes
    # PDF) -- esta prueba confirma que ahora SÍ llegan al contrato HTTP,
    # a diferencia de antes de esta ronda.
    # Ronda 58: section_title (Pista B.1 del ADR-003, ya poblado desde
    # antes) tampoco llegaba nunca a `sources` -- esta prueba confirma
    # que ahora sí llega, junto con page_start/page_end.
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    source = Source(
        project_id=_PROJECT_ID, title="Manual", source_type=SourceType.PDF,
        validation_status=SourceValidationStatus.VALIDADO,
    )
    SqlAlchemySourceRepository(paths).save(source)

    chunk = Chunk(
        project_id=_PROJECT_ID, source_id=source.id, chunk_index=0, text=_HORARIO_TEXT,
        token_count=12, page_start=3, page_end=4, section_title="Horario de atención",
    )
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

    client = _make_client(paths.base_dir)
    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["sources"]) == 1
    assert body["sources"][0]["page_start"] == 3
    assert body["sources"][0]["page_end"] == 4
    assert body["sources"][0]["section_title"] == "Horario de atención"


def test_post_message_returns_aclarar_when_a_required_variable_is_missing(tmp_path):
    paths = _publish_sample_project(tmp_path, required_variables=["plantel"])
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "aclarar"
    assert "plantel" in body["response_text"]
    assert body["sources"] == []  # no se buscó -- solo se busca si la decisión final es "responder"
    # Ronda 12: missing_variables permite que un canal (p. ej. el widget)
    # sepa a qué variable asociar la siguiente respuesta del visitante.
    assert body["missing_variables"] == ["plantel"]


def test_post_message_resolves_once_the_missing_variable_is_provided_on_a_second_call(tmp_path):
    # Simula lo que ahora hace el widget (Ronda 12): reenvía la consulta
    # ORIGINAL, esta vez con la variable que faltaba ya en `variables`.
    paths = _publish_sample_project(tmp_path, required_variables=["plantel"])
    client = _make_client(paths.base_dir)

    first = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    assert first.json()["action"] == "aclarar"

    second = client.post(
        f"/projects/{_PROJECT_ID}/messages",
        json={"message": "¿cuál es el horario de atención?", "variables": {"plantel": "Campus Norte"}},
    )
    body = second.json()
    assert body["action"] == "responder"
    assert body["missing_variables"] == []
    assert len(body["sources"]) == 1


# ---------- max_access_level: control de acceso en tiempo de consulta
# (Pista B.3 del ADR-003) ----------

_ADMIN_API_KEY = "secreto-admin-b3"


def test_a_widget_token_capped_below_the_source_access_level_gets_no_sources(tmp_path):
    # Fuente marcada CONFIDENCIAL -- un token de widget con techo
    # "publico" no debe poder verla: la respuesta se degrada a
    # "abstenerse" (ver SimulateConversation._search_and_filter), igual
    # que si la fuente no existiera para ese canal.
    paths = _publish_sample_project(tmp_path, access_level=AccessLevel.CONFIDENCIAL)
    client = _make_client(paths.base_dir, api_key=_ADMIN_API_KEY)
    admin_headers = {"X-API-Key": _ADMIN_API_KEY}

    capped_token = client.post(
        f"/projects/{_PROJECT_ID}/widget-tokens", json={"max_access_level": "publico"}, headers=admin_headers,
    ).json()["token"]

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
        headers={"X-Widget-Token": capped_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "abstenerse"
    assert body["sources"] == []


def test_an_uncapped_widget_token_still_sees_a_confidential_source(tmp_path):
    # Mismo proyecto/fuente que la prueba anterior, pero con un token
    # emitido SIN max_access_level (el comportamiento de siempre,
    # "restringido" -- sin techo) -- debe seguir viendo la fuente
    # confidencial con normalidad.
    paths = _publish_sample_project(tmp_path, access_level=AccessLevel.CONFIDENCIAL)
    client = _make_client(paths.base_dir, api_key=_ADMIN_API_KEY)
    admin_headers = {"X-API-Key": _ADMIN_API_KEY}

    uncapped_token = client.post(f"/projects/{_PROJECT_ID}/widget-tokens", headers=admin_headers).json()["token"]

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
        headers={"X-Widget-Token": uncapped_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "responder"
    assert len(body["sources"]) == 1


def test_post_message_persists_the_conversation_log(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    log_id = response.json()["log_id"]

    log_repository = SqlAlchemyConversationLogRepository(paths.base_dir / "runtime.db")
    entries = log_repository.list_for_project(_PROJECT_ID)
    assert len(entries) == 1
    assert entries[0].id == log_id
    assert entries[0].message == "¿cuál es el horario de atención?"
    assert entries[0].matched_intent == "Consultar horario"
    assert entries[0].snapshot_version == 1


# ---------- structured_result: enrutamiento multi-índice determinista
# (Pista B.4 del ADR-003) ----------

_COSTOS_ROWS = [{"plantel": "Campus Norte", "costo": "1500"}, {"plantel": "Campus Sur", "costo": "1800"}]


def _publish_project_with_structured_intent(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(_PROJECT_ID)

    source = Source(
        project_id=_PROJECT_ID, title="Costos", source_type=SourceType.XLSX,
        validation_status=SourceValidationStatus.VALIDADO,
    )
    SqlAlchemySourceRepository(paths).save(source)

    chunk = Chunk(
        project_id=_PROJECT_ID, source_id=source.id, chunk_index=0, text="costos", token_count=1,
        chunk_type=ChunkType.ESTRUCTURADO, section_title="costos",
        structured_content={"filas": _COSTOS_ROWS},
    )
    SqlAlchemyChunkRepository(paths).save_many(_PROJECT_ID, [chunk])

    intent = Intent(
        project_id=_PROJECT_ID, name="Consultar costos",
        positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    )
    SqlAlchemyIntentRepository(paths).save(intent)

    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=1, snapshot_dir=snapshot_dir),
    )
    return paths


def test_post_message_returns_structured_result_for_an_estructurado_intent(tmp_path):
    paths = _publish_project_with_structured_intent(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "cuánto cuesta la colegiatura"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "responder"
    assert body["sources"] == []  # vía estructurada resuelta -- nunca junto con fragmentos de texto
    assert body["structured_result"] is not None
    assert len(body["structured_result"]["rows"]) == 2
    assert {row["values"]["plantel"] for row in body["structured_result"]["rows"]} == {
        "Campus Norte", "Campus Sur",
    }
    # Pista C.2a del ADR-003: row_index distingue cada fila dentro del
    # bloque estructurado de origen -- aditivo, cruza al contrato HTTP.
    assert {row["row_index"] for row in body["structured_result"]["rows"]} == {0, 1}


def test_post_message_omits_structured_result_for_a_semantic_intent(tmp_path):
    # El campo es aditivo -- un agente que hoy solo lee 'sources' sigue
    # viendo exactamente el mismo contrato de siempre para una intención
    # SEMANTICO (el caso ya cubierto en el resto de esta suite).
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.json()["structured_result"] is None


# ---------- image_results: cierre del vacío 2 de la Ronda 66/68 (Fase 3 de
# multimodalidad nativa, RAG 3) ----------

def _publish_sample_project_with_image(tmp_path):
    """Mismo proyecto que `_publish_sample_project`, más una fuente
    IMAGEN_NATIVA ya indexada (vía RagService.index_image_source, el
    mismo comando real que usa RunPipeline) -- usa
    FakeImageEmbeddingProvider (no el FastEmbedImageProvider real) para
    poder indexar/buscar sin red ni descargar el modelo CLIP; el
    proceso HTTP que consulta esta instantánea debe construirse con
    `image_embedding_provider_factory=lambda cache_dir:
    FakeImageEmbeddingProvider()` (ver test más abajo) para que ambos
    lados -- indexación aquí, consulta en runtime_context.py -- caigan
    en el mismo espacio vectorial determinista."""
    paths = _publish_sample_project(tmp_path)

    source_repository = SqlAlchemySourceRepository(paths)
    image_source = Source(
        project_id=_PROJECT_ID, title="Logo institucional", source_type=SourceType.IMAGEN_NATIVA,
        validation_status=SourceValidationStatus.VALIDADO,
        original_copy_path=str(tmp_path / "originals" / "logo-institucional.png"),
    )
    source_repository.save(image_source)

    image_rag_service = RagService(
        SqlAlchemyChunkRepository(paths), WordOverlapFakeEmbeddingProvider(),
        QdrantLocalVectorStore(paths), SqlAlchemyIndexInfoRepository(paths),
        source_repository=source_repository, image_embedding_provider=FakeImageEmbeddingProvider(),
    )
    image_rag_service.index_image_source(_PROJECT_ID, image_source.id)

    # Re-publicar: la instantánea original ya se publicó dentro de
    # _publish_sample_project, ANTES de registrar/indexar esta fuente
    # de imagen -- FilesystemProjectSnapshotPublisher copia project.db
    # (donde vive el Source recién guardado) igual que cualquier otra
    # publicación; se sube a la versión 2 para que get_latest la sirva.
    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(_PROJECT_ID, 2)
    SqlAlchemyProjectSnapshotRepository(paths).save(
        ProjectSnapshot(project_id=_PROJECT_ID, version=2, snapshot_dir=snapshot_dir),
    )
    return paths, image_source


def _fake_image_embedding_provider_factory(_cache_dir):
    return FakeImageEmbeddingProvider()


def test_post_message_returns_image_results_when_the_project_has_an_indexed_image(tmp_path):
    paths, image_source = _publish_sample_project_with_image(tmp_path)
    client = _make_client(paths.base_dir, image_embedding_provider_factory=_fake_image_embedding_provider_factory)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "responder"
    # Tercer canal, nunca fusionado con 'sources' (texto) ni con
    # 'structured_result' -- ver docstring de MessageResponse.image_results.
    assert len(body["sources"]) == 1
    assert len(body["image_results"]) == 1
    image_result = body["image_results"][0]
    assert image_result["source_id"] == image_source.id
    assert image_result["image_relative_path"] == "logo-institucional.png"
    assert image_result["chunk_id"]
    assert image_result["score"] >= 0.0


def test_post_message_omits_image_results_without_an_image_embedding_provider_factory(tmp_path):
    # Sin image_embedding_provider_factory, create_app usa el default
    # real (FastEmbedImageProvider) -- pero el atajo de
    # SemanticSearchImages (VectorStore.count() == 0, ver Ronda 68)
    # evita cargar ese modelo real: esta instantánea SÍ tiene una
    # imagen indexada, pero fue indexada con FakeImageEmbeddingProvider
    # dentro de una colección Qdrant real -- un FastEmbedImageProvider
    # real consultando esa misma colección encontraría el punto
    # igualmente (el VectorStore no sabe qué embebedor produjo cada
    # vector), así que esta prueba usa deliberadamente un proyecto SIN
    # ninguna imagen indexada, para confirmar que el runtime por
    # defecto nunca intenta cargar el modelo CLIP real durante esta
    # suite (sin red disponible, embed_query_text fallaría con
    # EmbeddingProviderError si de verdad se invocara).
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.status_code == 200
    assert response.json()["image_results"] == []


def test_post_message_returns_a_conversation_id_when_none_is_given(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )

    assert response.json()["conversation_id"]


def test_post_message_reuses_the_conversation_id_across_two_calls(tmp_path):
    # Ronda 19: si el llamador reenvía el conversation_id que le dio la
    # primera respuesta, ambos turnos deben poder reconstruirse como una
    # sola conversación desde el repositorio.
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    first = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        f"/projects/{_PROJECT_ID}/messages",
        json={"message": "otra pregunta sobre el horario", "conversation_id": conversation_id},
    )

    assert second.json()["conversation_id"] == conversation_id
    log_repository = SqlAlchemyConversationLogRepository(paths.base_dir / "runtime.db")
    thread = log_repository.list_for_conversation(_PROJECT_ID, conversation_id)
    assert [entry.message for entry in thread] == [
        "¿cuál es el horario de atención?", "otra pregunta sobre el horario",
    ]


def test_post_message_without_reusing_the_conversation_id_creates_two_separate_conversations(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    first = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    second = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "otra pregunta sobre el horario"},
    )

    assert first.json()["conversation_id"] != second.json()["conversation_id"]


def test_post_message_returns_404_for_a_project_without_any_published_snapshot(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    client = _make_client(paths.base_dir)

    response = client.post("/projects/no-existe/messages", json={"message": "hola"})

    assert response.status_code == 404


def test_post_message_requires_the_configured_api_key(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key="secreto")

    unauthorized = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
    assert unauthorized.status_code == 401

    authorized = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"}, headers={"X-API-Key": "secreto"},
    )
    assert authorized.status_code == 200


def test_post_message_without_a_configured_api_key_does_not_require_the_header(tmp_path):
    # Sin api_key configurada (por ejemplo, en pruebas locales) el
    # endpoint sigue funcionando sin encabezado -- ver docstring de
    # create_app_from_env sobre por qué SÍ es obligatoria al desplegar.
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
    assert response.status_code == 200


def test_get_latest_reuses_the_cached_snapshot_across_requests(tmp_path):
    paths = _publish_sample_project(tmp_path)
    calls: list[str] = []

    def counting_factory(profile, _cache_dir):
        calls.append(profile)
        return WordOverlapFakeEmbeddingProvider()

    app = create_app(paths.base_dir, embedding_provider_factory=counting_factory)
    client = TestClient(app)

    client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"})
    client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "otra pregunta sobre el horario"})

    # Un solo proveedor de embeddings construido para las dos solicitudes
    # -- la instantánea v1 se calienta una vez y se reutiliza (ADR-002,
    # sección 5, riesgo de arranque en frío / conexión por llamada).
    assert len(calls) == 1


# ---------- GET /projects/{id}/metrics: observabilidad básica
# (Pista C.1 del ADR-003, opcional, no bloqueante) ----------

def test_get_metrics_requires_the_configured_api_key(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key="secreto")

    unauthorized = client.get(f"/projects/{_PROJECT_ID}/metrics")
    assert unauthorized.status_code == 401

    authorized = client.get(f"/projects/{_PROJECT_ID}/metrics", headers={"X-API-Key": "secreto"})
    assert authorized.status_code == 200


def test_get_metrics_is_not_reachable_with_a_widget_token(tmp_path):
    # Mismo criterio que /widget-tokens: esta es una capacidad
    # administrativa, nunca acotada a un solo proyecto vía
    # X-Widget-Token -- solo la API key global la abre.
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key=_ADMIN_API_KEY)
    admin_headers = {"X-API-Key": _ADMIN_API_KEY}
    widget_token = client.post(f"/projects/{_PROJECT_ID}/widget-tokens", headers=admin_headers).json()["token"]

    response = client.get(f"/projects/{_PROJECT_ID}/metrics", headers={"X-Widget-Token": widget_token})

    assert response.status_code == 401


def test_get_metrics_without_a_configured_api_key_does_not_require_the_header(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/metrics")

    assert response.status_code == 200


def test_get_metrics_reflects_real_turns_persisted_by_post_message(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"})
    client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "pregunta sin ninguna coincidencia real"})

    response = client.get(f"/projects/{_PROJECT_ID}/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == _PROJECT_ID
    assert body["since"] is None
    assert body["total_turns"] == 2
    assert sum(body["turns_by_action"].values()) == 2
    assert body["avg_latency_ms"] is not None  # HandleIncomingMessage siempre mide latencia real
    # Percentiles (Ronda 44, Pista C.5 del ADR-003): con al menos un
    # turno con latencia capturada, p95/p99 tampoco son None.
    assert body["p95_latency_ms"] is not None
    assert body["p99_latency_ms"] is not None


def test_get_metrics_on_a_project_without_any_turn_returns_none_averages(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_turns"] == 0
    assert body["avg_latency_ms"] is None
    assert body["p95_latency_ms"] is None
    assert body["p99_latency_ms"] is None
    assert body["abstention_rate"] is None


def test_get_metrics_filters_by_the_since_query_parameter(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"})

    from datetime import datetime, timedelta, timezone
    future = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.get(f"/projects/{_PROJECT_ID}/metrics", params={"since": future.isoformat()})

    assert response.status_code == 200
    # since en el futuro -- ningún turno real puede haber ocurrido ya
    # después de ese instante.
    assert response.json()["total_turns"] == 0


# ---------- GET /projects/{id}/quality: doble validación de calidad
# para el agente externo de pruebas de NEXOM (Ronda 59, roadmap de
# preparación RAG 3-5, opcional, no bloqueante) ----------

def _save_complete_run(paths, *, started_at, expected_source_rank):
    # Un único caso con expected_source_id declarado (retrieval_check_
    # applicable=True) -- suficiente para ejercitar recall_at_k(3) y
    # mean_reciprocal_rank() sin construir un banco de pruebas completo.
    item = EvaluationResultItem(
        test_case_id="tc1", test_case_code="TC-1", category=TestCategory.RESPUESTA_DIRECTA,
        verdict=EvaluationVerdict.VERDE if expected_source_rank == 1 else EvaluationVerdict.AMARILLO,
        retrieval_check_applicable=True, expected_source_rank=expected_source_rank,
    )
    run = EvaluationRun(project_id=_PROJECT_ID, scope="completa", items=[item], started_at=started_at)
    SqlAlchemyEvaluationRunRepository(paths).save(run)
    return run


def test_get_quality_requires_the_configured_api_key(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key="secreto")

    unauthorized = client.get(f"/projects/{_PROJECT_ID}/quality")
    assert unauthorized.status_code == 401

    authorized = client.get(f"/projects/{_PROJECT_ID}/quality", headers={"X-API-Key": "secreto"})
    assert authorized.status_code == 200


def test_get_quality_is_not_reachable_with_a_widget_token(tmp_path):
    # Mismo criterio que /metrics: capacidad administrativa, nunca
    # acotada a un solo proyecto vía X-Widget-Token.
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key=_ADMIN_API_KEY)
    admin_headers = {"X-API-Key": _ADMIN_API_KEY}
    widget_token = client.post(f"/projects/{_PROJECT_ID}/widget-tokens", headers=admin_headers).json()["token"]

    response = client.get(f"/projects/{_PROJECT_ID}/quality", headers={"X-Widget-Token": widget_token})

    assert response.status_code == 401


def test_get_quality_without_a_configured_api_key_does_not_require_the_header(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/quality")

    assert response.status_code == 200


def test_get_quality_on_a_project_without_any_complete_run_returns_has_complete_run_false(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == _PROJECT_ID
    assert body["has_complete_run"] is False
    assert body["last_run_id"] is None
    assert body["recall_at_3"] is None
    assert body["mrr"] is None
    assert body["regression_gate_passed"] is None


def test_get_quality_reflects_the_latest_complete_run(tmp_path):
    from datetime import datetime, timezone

    paths = _publish_sample_project(tmp_path)
    run = _save_complete_run(paths, started_at=datetime.now(timezone.utc), expected_source_rank=1)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["has_complete_run"] is True
    assert body["last_run_id"] == run.id
    assert body["overall_verdict"] == "verde"
    assert body["has_blocking_failures"] is False
    assert body["recall_at_3"] == 1.0
    assert body["mrr"] == 1.0
    # Menos de dos corridas "completa" -- la compuerta se da por
    # cumplida por falta de datos, mismo criterio que
    # evaluate_release_gates.py::_retrieval_regression_gate.
    assert body["regression_gate_passed"] is True


def test_get_quality_regression_gate_blocks_on_a_real_drop_above_the_default_threshold(tmp_path):
    from datetime import datetime, timedelta, timezone

    paths = _publish_sample_project(tmp_path)
    now = datetime.now(timezone.utc)
    # Referencia: primer lugar (MRR 1.0). Corrida más reciente: tercer
    # lugar (MRR 1/3) -- caída relativa de ~67%, muy por encima del
    # umbral por defecto (15%).
    _save_complete_run(paths, started_at=now - timedelta(hours=1), expected_source_rank=1)
    _save_complete_run(paths, started_at=now, expected_source_rank=3)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["regression_gate_passed"] is False
    assert "umbral configurado" in body["regression_gate_reason"]


def test_get_quality_regression_gate_uses_the_projects_custom_threshold(tmp_path):
    from datetime import datetime, timedelta, timezone

    paths = _publish_sample_project(tmp_path)
    # Mismo escenario que la prueba anterior (caída de ~67% en MRR),
    # pero con un umbral de proyecto explícito lo bastante alto para
    # que esta vez SÍ pase -- confirma que el endpoint lee Project.
    # quality_regression_threshold, no solo el valor por defecto de la
    # instalación.
    SqlAlchemyProjectRepository(paths).save(
        Project(id=_PROJECT_ID, name="Proyecto de prueba", quality_regression_threshold=0.9),
    )
    now = datetime.now(timezone.utc)
    _save_complete_run(paths, started_at=now - timedelta(hours=1), expected_source_rank=1)
    _save_complete_run(paths, started_at=now, expected_source_rank=3)
    client = _make_client(paths.base_dir)

    response = client.get(f"/projects/{_PROJECT_ID}/quality")

    assert response.status_code == 200
    assert response.json()["regression_gate_passed"] is True


# ---------- POST /projects/{id}/messages/{log_id}/feedback: captura de
# señal de relevancia (Pista C.4a del ADR-003, opcional) ----------

def _post_message_and_get_log_id(client) -> tuple[str, str]:
    response = client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
    )
    body = response.json()
    source_id = body["sources"][0]["source_id"]
    return body["log_id"], source_id


def test_post_feedback_records_a_relevant_signal_with_agente_externo_origin(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    log_id, source_id = _post_message_and_get_log_id(client)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [{"source_id": source_id, "signal": "relevante"}]},
    )

    assert response.status_code == 200
    assert response.json()["recorded"] == 1

    feedback_repository = SqlAlchemyRetrievalFeedbackRepository(paths.base_dir / "runtime.db")
    [entry] = feedback_repository.list_for_log_entry(log_id)
    assert entry.source_id == source_id
    assert entry.signal.value == "relevante"
    assert entry.origin.value == "agente_externo"


def test_post_feedback_accepts_citado_en_respuesta_only_via_this_endpoint(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    log_id, source_id = _post_message_and_get_log_id(client)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [{"source_id": source_id, "signal": "citado_en_respuesta"}]},
    )

    assert response.status_code == 200
    feedback_repository = SqlAlchemyRetrievalFeedbackRepository(paths.base_dir / "runtime.db")
    assert feedback_repository.list_for_log_entry(log_id)[0].signal.value == "citado_en_respuesta"


def test_post_feedback_records_more_than_one_entry_in_a_single_call(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    log_id, source_id = _post_message_and_get_log_id(client)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [
            {"source_id": source_id, "signal": "relevante"},
            {"source_id": source_id, "signal": "citado_en_respuesta", "notes": "usado en la respuesta"},
        ]},
    )

    assert response.status_code == 200
    assert response.json()["recorded"] == 2


def test_post_feedback_rejects_an_unknown_signal_value(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)
    log_id, source_id = _post_message_and_get_log_id(client)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [{"source_id": source_id, "signal": "muy_relevante"}]},
    )

    assert response.status_code == 422


def test_post_feedback_returns_404_for_a_log_id_that_does_not_exist(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir)

    response = client.post(
        f"/projects/{_PROJECT_ID}/messages/log-inexistente/feedback",
        json={"entries": [{"source_id": "src-1", "signal": "relevante"}]},
    )

    assert response.status_code == 404


def test_post_feedback_requires_the_configured_api_key(tmp_path):
    paths = _publish_sample_project(tmp_path)
    client = _make_client(paths.base_dir, api_key="secreto")
    unauthorized_post = client.post(f"/projects/{_PROJECT_ID}/messages", json={"message": "hola"})
    assert unauthorized_post.status_code == 401  # confirma que ya no hay ningún turno sin API key

    authorized_client = _make_client(paths.base_dir, api_key="secreto")
    log_id, source_id = "log-cualquiera", "src-cualquiera"
    unauthorized = authorized_client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [{"source_id": source_id, "signal": "relevante"}]},
    )
    assert unauthorized.status_code == 401


def test_post_feedback_is_reachable_with_a_widget_token_scoped_to_the_project(tmp_path):
    # A diferencia de /metrics (solo API key): mismo criterio que
    # /messages -- el agente conversacional externo, que ya llama a
    # /messages con su X-Widget-Token, debe poder reportar feedback con
    # esa misma credencial (nota de cierre de C.4a, 2026-08-20).
    paths = _publish_sample_project(tmp_path)
    admin_client = _make_client(paths.base_dir, api_key=_ADMIN_API_KEY)
    admin_headers = {"X-API-Key": _ADMIN_API_KEY}
    widget_token = admin_client.post(
        f"/projects/{_PROJECT_ID}/widget-tokens", headers=admin_headers,
    ).json()["token"]
    widget_headers = {"X-Widget-Token": widget_token}

    message_response = admin_client.post(
        f"/projects/{_PROJECT_ID}/messages", json={"message": "¿cuál es el horario de atención?"},
        headers=widget_headers,
    )
    log_id = message_response.json()["log_id"]
    source_id = message_response.json()["sources"][0]["source_id"]

    response = admin_client.post(
        f"/projects/{_PROJECT_ID}/messages/{log_id}/feedback",
        json={"entries": [{"source_id": source_id, "signal": "relevante"}]},
        headers=widget_headers,
    )

    assert response.status_code == 200
