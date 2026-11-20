"""Ronda 106 (autorizada por NEXOM): equivalencia Simulador–Runtime del
procedimiento de recuperación, con la MISMA instantánea, la misma
configuración y las mismas consultas.

- Escritorio: ConversationalService armado como app/bootstrap.py, con el
  lector del procedimiento sobre el proyecto de la instalación.
- Runtime: create_app sobre la instantánea publicada de ese proyecto (lee el
  procedimiento del project.db de la instantánea).

Corpus mínimo con filtro de metadatos y un fragmento puente: un plan con
una sección «Requisitos de ingreso» que solo remite a requisitos_ingreso.md,
el documento referido (con un fragmento solo-YAML) y otra sección del plan."""
from __future__ import annotations

import pytest

from application.conversational.service import ConversationalService
from application.metadata.service import MetadataService
from application.rag.service import RagService
from domain.conversational.entities import ConversationalVariable, Intent
from domain.documents.entities import Source, SourceType, SourceValidationStatus
from domain.ingestion.entities import Chunk
from domain.projects.entities import ConfigurationEntry, Project
from domain.rag.entities import VectorPoint
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
from infrastructure.database.repositories import (
    ProjectAgentRerankingReader, ProjectRetrievalProcedureReader, SqlAlchemyConfigurationRepository,
    SqlAlchemyProjectRepository,
)
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from interfaces.api.app import create_app

from tests.unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

P = "p-r106"
KEY = "clave-r106"
YAML = "---\nnivel: bachillerato\n---\n"
FRAGMENTOS = [
    # (fuente, título de sección, texto)
    ("plan_a.md", "Requisitos de ingreso",
     "Los requisitos de ingreso al bachillerato están en requisitos_ingreso.md para evitar duplicación."),
    ("plan_a.md", "Información general", "Información general del bachillerato: plan semestral, dos planteles."),
    ("requisitos_ingreso.md", None,
     YAML + "# Documentos — Bachillerato\nActa de nacimiento, CURP, certificado de secundaria y fotografías."),
    ("requisitos_ingreso.md", None, YAML),
]
CONSULTAS = [
    "¿Cuáles son los requisitos de ingreso al bachillerato?",
    "¿Qué documentos necesito para entrar al bachillerato?",
    "información general del bachillerato",
]


def _instalacion(tmp_path, procedimiento, embedder):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    paths.ensure_project_layout(P)
    SqlAlchemyProjectRepository(paths).save(Project(id=P, name="Equivalencia r106"))
    if procedimiento is not None:
        SqlAlchemyConfigurationRepository(paths).save(
            ConfigurationEntry(project_id=P, key="retrieval_procedure", value=procedimiento))
    fuentes = SqlAlchemySourceRepository(paths)
    meta = MetadataService(SqlAlchemyMetadataSchemaRepository(paths), SqlAlchemyCatalogRepository(paths),
                           SqlAlchemySourceMetadataRepository(paths), fuentes)
    sid = meta.create_schema(P).id
    nivel = meta.create_catalog(P, "nivel")
    meta.add_catalog_entry(P, nivel.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(P, sid, "nivel_academico", "Nivel académico", "seleccion_unica",
                              inherited_by_chunks=True, catalog_id=nivel.id)
    ids = {}
    for titulo in ("plan_a.md", "requisitos_ingreso.md"):
        fuente = Source(project_id=P, title=titulo, source_type=SourceType.MARKDOWN,
                        validation_status=SourceValidationStatus.VALIDADO)
        fuentes.save(fuente)
        meta.set_source_metadata_value(P, sid, fuente.id, "nivel_academico", "bachillerato")
        ids[titulo] = fuente.id
    chunks = [Chunk(project_id=P, source_id=ids[f], chunk_index=i, text=t, token_count=len(t.split()),
                    section_title=s) for i, (f, s, t) in enumerate(FRAGMENTOS)]
    SqlAlchemyChunkRepository(paths).save_many(P, chunks)
    store = QdrantLocalVectorStore(paths)
    vectores = embedder.embed_texts([c.text for c in chunks])
    store.ensure_collection(P, vector_size=len(vectores[0]))
    store.upsert(P, [VectorPoint(id=c.id, vector=v, payload={"source_id": c.source_id})
                     for c, v in zip(chunks, vectores, strict=True)])
    SqlAlchemyConversationalVariableRepository(paths).save(ConversationalVariable(
        project_id=P, code="nivel_academico", label="Nivel académico", metadata_field_id="nivel_academico"))
    intents = SqlAlchemyIntentRepository(paths)
    intents.save(Intent(project_id=P, name="Consultar requisitos de ingreso",
                        description="Requisitos de ingreso y documentos para entrar.",
                        positive_examples=["¿Cuáles son los requisitos de ingreso?", "¿Qué documentos necesito?"],
                        optional_variables=["nivel_academico"]))
    intents.save(Intent(project_id=P, name="Consultar información general",
                        description="Información general del programa.",
                        positive_examples=["información general", "¿Cómo es el programa?"],
                        optional_variables=["nivel_academico"]))
    snapshot_dir = FilesystemProjectSnapshotPublisher(paths).publish(P, 1)
    SqlAlchemyProjectSnapshotRepository(paths).save(ProjectSnapshot(project_id=P, version=1, snapshot_dir=snapshot_dir))
    return paths, ids


def _escritorio(paths, embedder):
    """Mismo armado que app/bootstrap.py."""
    rag = RagService(SqlAlchemyChunkRepository(paths), embedder, QdrantLocalVectorStore(paths),
                     SqlAlchemyIndexInfoRepository(paths), source_repository=SqlAlchemySourceRepository(paths))
    return ConversationalService(
        SqlAlchemyIntentRepository(paths), SqlAlchemyConversationalVariableRepository(paths),
        SqlAlchemyGuardrailRuleRepository(paths), SqlAlchemyChannelingSchemeRepository(paths),
        SqlAlchemySourceMetadataRepository(paths), rag, source_repository=SqlAlchemySourceRepository(paths),
        schema_repository=SqlAlchemyMetadataSchemaRepository(paths), catalog_repository=SqlAlchemyCatalogRepository(paths),
        agent_reranking=ProjectAgentRerankingReader(paths), retrieval_procedure=ProjectRetrievalProcedureReader(paths),
    )


def _runtime(paths, embedder):
    return TestClient(create_app(paths.base_dir, api_key=KEY, embedding_provider_factory=lambda _p, _c: embedder))


@pytest.mark.parametrize("procedimiento, esperado", [(None, "r105b"), ("r105b", "r105b"), ("r106", "r106")])
def test_simulador_y_runtime_aplican_el_mismo_procedimiento(tmp_path, procedimiento, esperado):
    embedder = WordOverlapFakeEmbeddingProvider()
    paths, ids = _instalacion(tmp_path, procedimiento, embedder)
    escritorio = _escritorio(paths, embedder)
    cliente = _runtime(paths, embedder)
    for consulta in CONSULTAS:
        traza = escritorio.simulate(P, consulta)
        cuerpo = cliente.post(f"/projects/{P}/messages", json={"message": consulta},
                              headers={"X-API-Key": KEY}).json()
        assert traza.applied_metadata_filters == {"nivel_academico": "bachillerato"}, consulta
        assert [r.chunk.id for r in traza.search_results] == [s["chunk_id"] for s in cuerpo["sources"]], consulta
        assert [round(r.score, 9) for r in traza.search_results] == [round(s["score"], 9) for s in cuerpo["sources"]]
        assert traza.action.value == cuerpo["action"]
        ejecucion = cuerpo["execution"]
        assert traza.retrieval_pipeline == ejecucion["retrieval_pipeline"] == esperado
        assert [list(o.referenced_from) for o in traza.result_ordering] == \
            [r["referenced_from"] for r in ejecucion["results"]]
        assert [o.retrieval_rank for o in traza.result_ordering] == [r["retrieval_rank"] for r in ejecucion["results"]]
    detalles = cliente.get("/health/details", headers={"X-API-Key": KEY}).json()
    assert [s["retrieval_pipeline"] for s in detalles["loaded_snapshots"]] == [esperado]
    publico = cliente.get("/health").json()
    assert publico["retrieval_pipeline"] == "r106" and publico["retrieval_pipelines_supported"] == ["r105b", "r106"]


def test_r106_requisitos_delante_del_puente_en_simulador_y_runtime(tmp_path):
    embedder = WordOverlapFakeEmbeddingProvider()
    paths, ids = _instalacion(tmp_path, "r106", embedder)
    traza = _escritorio(paths, embedder).simulate(P, CONSULTAS[0])
    fuentes = [r.chunk.source_id for r in traza.search_results]
    puente = next(i for i, r in enumerate(traza.search_results) if "requisitos_ingreso.md" in r.chunk.text)
    assert fuentes.index(ids["requisitos_ingreso.md"]) < puente
    vista = traza.result_ordering[fuentes.index(ids["requisitos_ingreso.md"])]
    assert vista.referenced_from_sources == ["plan_a.md"]
    # Y: el fragmento solo-YAML no tiene título de afinidad.
    assert all(o.affinity == 0 for r, o in zip(traza.search_results, traza.result_ordering, strict=True)
               if r.chunk.text == YAML)


def test_el_runtime_usa_el_procedimiento_de_la_instantanea_no_el_del_proyecto_en_edicion(tmp_path):
    """Cambiar el ajuste en el proyecto no altera la versión publicada: llega
    al Runtime al publicar una versión nueva (mismo criterio que P1)."""
    embedder = WordOverlapFakeEmbeddingProvider()
    paths, _ids = _instalacion(tmp_path, "r105b", embedder)
    SqlAlchemyConfigurationRepository(paths).save(
        ConfigurationEntry(project_id=P, key="retrieval_procedure", value="r106", version=2))
    assert _escritorio(paths, embedder).simulate(P, CONSULTAS[0]).retrieval_pipeline == "r106"
    cuerpo = _runtime(paths, embedder).post(f"/projects/{P}/messages", json={"message": CONSULTAS[0]},
                                            headers={"X-API-Key": KEY}).json()
    assert cuerpo["execution"]["retrieval_pipeline"] == "r105b"


def test_procedimiento_desconocido_falla_explicito_en_simulador_y_runtime(tmp_path):
    from domain.conversational.retrieval_procedure import UnknownRetrievalProcedureError

    embedder = WordOverlapFakeEmbeddingProvider()
    paths, _ids = _instalacion(tmp_path, "r999", embedder)
    with pytest.raises(UnknownRetrievalProcedureError):
        _escritorio(paths, embedder).simulate(P, CONSULTAS[0])
    respuesta = _runtime(paths, embedder).post(f"/projects/{P}/messages", json={"message": CONSULTAS[0]},
                                               headers={"X-API-Key": KEY})
    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["code"] == "configuration.retrieval_procedure_unknown"


def test_el_ajuste_viaja_con_el_agentproj_y_con_la_copia(tmp_path):
    """El procedimiento se guarda en el project.db: exportar e importar (también
    como copia con identificador nuevo) lo conserva."""
    import uuid

    from app.lifecycle import shutdown, start

    origen = start(base_dir=tmp_path / "a")
    destino = start(base_dir=tmp_path / "b")
    try:
        proyecto = origen.project_service.create_project("Viaja")
        assert origen.project_service.get_retrieval_procedure(proyecto.id) == ("r106", True)
        origen.project_service.update_retrieval_procedure(proyecto.id, "r105b")
        paquete = str(tmp_path / "viaja.agentproj")
        origen.project_service.export_project(proyecto.id, paquete)
        importado = destino.project_service.import_project(paquete, identity_policy="preserve")
        assert destino.project_service.get_retrieval_procedure(importado.id) == ("r105b", True)
        copia = destino.project_service.import_project(
            paquete, new_project_id=str(uuid.uuid4()), new_name="Copia", identity_policy="fork",
        )
        assert copia.id != proyecto.id
        assert destino.project_service.get_retrieval_procedure(copia.id) == ("r105b", True)
    finally:
        shutdown(origen)
        shutdown(destino)
