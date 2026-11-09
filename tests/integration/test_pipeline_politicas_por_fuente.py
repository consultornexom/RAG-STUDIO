"""Ronda 98 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato):
pipeline completo con fuentes de tres tipos documentales y tres políticas
distintas, sobre un AppContext real (SQLite real, extractor real, Qdrant
local real; solo el proveedor de embeddings es determinístico para no
depender de red).

Antes, la pestaña Pipeline enviaba UN document_type_code y la política de
ese tipo se aplicaba a todas las fuentes; y la incrementalidad solo miraba
el hash del archivo, así que cambiar la política o los metadatos heredados
no reprocesaba nada."""
from __future__ import annotations

import pytest

from application.conversational.queries.simulate_conversation import SimulateConversation
from application.pipeline.commands.run_pipeline import RunPipeline
from application.rag.service import RagService
from domain.conversational.entities import ConversationalVariable, Intent
from domain.documents.entities import SourceType
from domain.ingestion.entities import ChunkType, FragmentationStrategy
from domain.pipeline.entities import PER_SOURCE_DOCUMENT_TYPE, PipelineItemStatus, PipelineRunStatus
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository,
    SqlAlchemyConversationalVariableRepository,
    SqlAlchemyGuardrailRuleRepository,
    SqlAlchemyIntentRepository,
)
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.metadata_repositories import (
    SqlAlchemyCatalogRepository,
    SqlAlchemyMetadataSchemaRepository,
    SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.pipeline_repositories import SqlAlchemyPipelineRunRepository
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

from ..unit.application.fakes_rag import WordOverlapFakeEmbeddingProvider

PROGRAMA = (
    "# Plan de estudios\nAsignaturas del bachillerato {plantel} por semestre.\n\n"
    "# Perfil de egreso\nCompetencias del egresado del plantel {plantel}.\n\n"
    "# Campo de trabajo\nContinuar estudios universitarios desde {plantel}.\n"
)


class Lote:
    def __init__(self, ctx, tmp_path):
        self.ctx, self.tmp = ctx, tmp_path
        paths = ctx.paths
        self.runs = SqlAlchemyPipelineRunRepository(paths)
        self.rag = RagService(
            SqlAlchemyChunkRepository(paths), WordOverlapFakeEmbeddingProvider(), QdrantLocalVectorStore(paths),
            SqlAlchemyIndexInfoRepository(paths), source_repository=SqlAlchemySourceRepository(paths),
        )
        self.pipeline = RunPipeline(SqlAlchemySourceRepository(paths), ctx.ingestion_service, self.rag, self.runs)
        self.pid = ctx.project_service.create_project("AGENTE UDL - LOTE01_Bachillerato").id
        meta = ctx.metadata_service
        self.schema_id = meta.create_schema(self.pid).id
        cat = meta.create_catalog(self.pid, "campus_udl")
        meta.add_catalog_entry(self.pid, cat.id, "hilario_medina", "Hilario Medina")
        meta.add_catalog_entry(self.pid, cat.id, "torres_landa", "Torres Landa")
        meta.add_field_definition(self.pid, self.schema_id, "campus", "Campus o plantel", "seleccion_multiple",
                                  multiple=True, filterable=True, inherited_by_chunks=True, catalog_id=cat.id)
        ing = ctx.ingestion_service
        ing.set_fragmentation_policy(self.pid, "programa_academico", strategy=FragmentationStrategy.POR_ENCABEZADO,
                                     target_tokens=500, overlap_tokens=0, min_tokens=1)
        for tipo in ("informacion_academica", "informacion_admisiones"):
            ing.set_fragmentation_policy(self.pid, tipo, strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
        self.ids: dict[str, str] = {}
        self.fuente("programa_hm", "programa_academico", PROGRAMA.format(plantel="Hilario Medina"), ["hilario_medina"])
        self.fuente("programa_tl", "programa_academico", PROGRAMA.format(plantel="Torres Landa"), ["torres_landa"])
        ambos = ["hilario_medina", "torres_landa"]
        self.fuente("calendario", "informacion_academica",
                    "# Calendario\nInicio de clases en agosto.\n\n# Vacaciones\nPeriodo vacacional en diciembre.\n", ambos)
        self.fuente("reglamento", "informacion_academica",
                    "# Reglamento\nAsistencia mínima del 80 por ciento.\n\n# Bajas\nTrámite de baja temporal.\n", ambos)
        self.fuente("requisitos_ingreso", "informacion_admisiones",
                    "# Requisitos de ingreso\nCertificado de secundaria y acta de nacimiento.\n\n"
                    "# Entrega\nEn ventanilla de admisiones.\n", ambos)

    def fuente(self, nombre, tipo, texto, campus):
        ruta = self.tmp / f"{nombre}.md"
        ruta.write_text(texto, encoding="utf-8")
        src = self.ctx.document_service.register_source(
            self.pid, f"{nombre}.md", SourceType.MARKDOWN, location=str(ruta), document_type_code=tipo,
        )
        for estado in ("en_revision", "validado"):
            self.ctx.document_service.update_validation_status(self.pid, src.id, estado)
        self.ids[nombre] = src.id
        self.ctx.metadata_service.set_source_metadata_value(self.pid, self.schema_id, src.id, "campus", campus)

    def correr(self):
        return self.pipeline.execute(self.pid, schema_id=self.schema_id)

    def item(self, run, nombre):
        return next(i for i in run.items if i.source_id == self.ids[nombre])

    def chunks(self, nombre):
        return [c for c in self.ctx.ingestion_service.list_chunks(self.pid, self.ids[nombre])
                if c.chunk_type != ChunkType.PADRE]


@pytest.fixture
def lote(app_context, tmp_path):
    return Lote(app_context, tmp_path)


def test_cada_fuente_usa_la_politica_de_su_tipo_en_la_misma_corrida(lote):
    run = lote.correr()
    assert run.status == PipelineRunStatus.COMPLETO
    assert run.document_type_code == PER_SOURCE_DOCUMENT_TYPE
    esperado = {
        "programa_hm": ("programa_academico", "por_encabezado"),
        "programa_tl": ("programa_academico", "por_encabezado"),
        "calendario": ("informacion_academica", "documento_completo"),
        "reglamento": ("informacion_academica", "documento_completo"),
        "requisitos_ingreso": ("informacion_admisiones", "documento_completo"),
    }
    for nombre, (tipo, estrategia) in esperado.items():
        item = lote.item(run, nombre)
        assert item.status == PipelineItemStatus.EXITOSO, item.error
        assert (item.document_type_code, item.policy_document_type_code, item.policy_strategy) == (tipo, tipo, estrategia)
        assert item.policy_origin == "especifica"
        assert item.reason == "Fuente nueva o nunca procesada con éxito."

    # Cantidad y contenido de fragmentos según la estrategia de cada tipo.
    for nombre in ("programa_hm", "programa_tl"):
        assert [c.section_title for c in lote.chunks(nombre)] == ["Plan de estudios", "Perfil de egreso", "Campo de trabajo"]
    for nombre in ("calendario", "reglamento", "requisitos_ingreso"):
        [unico] = lote.chunks(nombre)
        assert "#" in unico.text and unico.text.count("\n") >= 3  # documento completo, sin dividir por encabezado
    assert "Torres Landa" in " ".join(c.text for c in lote.chunks("programa_tl"))

    # Metadatos heredados, incluido el valor múltiple.
    assert {c.inherited_metadata["campus"] for c in lote.chunks("requisitos_ingreso")} == {"hilario_medina|torres_landa"}
    assert {c.inherited_metadata["campus"] for c in lote.chunks("programa_hm")} == {"hilario_medina"}

    # Persistencia de la traza (migración 0022).
    guardado = lote.runs.get(lote.pid, run.id)
    assert lote.item(guardado, "calendario").policy_strategy == "documento_completo"
    assert lote.item(guardado, "calendario").chunks_digest


def test_regresion_incrementalidad_por_configuracion(lote):
    primera = lote.correr()
    assert all(i.status == PipelineItemStatus.EXITOSO for i in primera.items)

    # 1. Archivo y configuración sin cambios -> omitir.
    segunda = lote.correr()
    assert all(i.status == PipelineItemStatus.OMITIDO for i in segunda.items)
    assert all(i.reason.startswith("Sin cambios") for i in segunda.items)

    # 2. Archivo sin cambios y política modificada -> reprocesar solo ese tipo.
    lote.ctx.ingestion_service.set_fragmentation_policy(
        lote.pid, "informacion_academica", strategy=FragmentationStrategy.POR_ENCABEZADO,
        target_tokens=500, overlap_tokens=0, min_tokens=1,
    )
    tercera = lote.correr()
    reprocesadas = {n for n in lote.ids if lote.item(tercera, n).status == PipelineItemStatus.EXITOSO}
    assert reprocesadas == {"calendario", "reglamento"}
    assert "Cambió la política de fragmentación" in lote.item(tercera, "calendario").reason
    assert len(lote.chunks("calendario")) == 2

    # 3. Archivo sin cambios y metadatos heredados modificados -> actualizar fragmentos e índice.
    lote.ctx.metadata_service.remove_source_metadata_value_item(
        lote.pid, lote.schema_id, lote.ids["requisitos_ingreso"], "campus", "hilario_medina",
    )
    cuarta = lote.correr()
    item = lote.item(cuarta, "requisitos_ingreso")
    assert item.status == PipelineItemStatus.EXITOSO
    assert item.steps_completed == ["extraccion", "fragmentacion", "indexacion"]
    assert "Cambiaron los metadatos que heredan los fragmentos." in item.reason
    assert {c.inherited_metadata["campus"] for c in lote.chunks("requisitos_ingreso")} == {"torres_landa"}
    assert {n for n in lote.ids if lote.item(cuarta, n).status == PipelineItemStatus.EXITOSO} == {"requisitos_ingreso"}

    # 4. Archivo modificado -> reprocesar.
    # Se modifica el archivo que RAG Studio extrae (su copia en sources/original/).
    fuente_hm = lote.ctx.document_service.get_source(lote.pid, lote.ids["programa_hm"])
    from pathlib import Path
    Path(fuente_hm.original_copy_path or fuente_hm.location).write_text(PROGRAMA.format(plantel="Hilario Medina") + "\n# Becas\nApoyos económicos para alumnos del plantel con buen promedio.\n",
                                             encoding="utf-8")
    quinta = lote.correr()
    assert lote.item(quinta, "programa_hm").status == PipelineItemStatus.EXITOSO
    assert lote.item(quinta, "programa_hm").reason == "El archivo cambió."
    assert len(lote.chunks("programa_hm")) == 4

    # 5. Reejecución sin cambios posteriores -> omitir todo.
    sexta = lote.correr()
    assert all(i.status == PipelineItemStatus.OMITIDO for i in sexta.items)


def test_fragmentar_a_mano_con_otra_politica_no_queda_oculto(lote):
    lote.correr()
    lote.ctx.ingestion_service.fragment_source(
        lote.pid, lote.ids["programa_tl"], schema_id=lote.schema_id, document_type_code="informacion_academica",
    )
    run = lote.correr()
    item = lote.item(run, "programa_tl")
    assert item.status == PipelineItemStatus.EXITOSO
    assert "cambiaron fuera del pipeline" in item.reason
    assert len(lote.chunks("programa_tl")) == 3


def test_vista_previa_no_procesa_nada_y_anticipa_la_decision(lote):
    plan = lote.pipeline.plan(lote.pid, schema_id=lote.schema_id)
    assert {f["accion"] for f in plan} == {"reprocesar"}
    assert lote.runs.list_for_project(lote.pid) == []
    assert lote.ctx.ingestion_service.list_chunks(lote.pid, lote.ids["calendario"]) == []
    fila = next(f for f in plan if f["source_id"] == lote.ids["calendario"])
    assert fila["document_type_code"] == "informacion_academica"
    assert fila["policy"].startswith("informacion_academica (documento_completo")
    lote.correr()
    assert {f["accion"] for f in lote.pipeline.plan(lote.pid, schema_id=lote.schema_id)} == {"omitir"}


def test_la_busqueda_filtrada_recupera_documentos_de_ambos_planteles(lote):
    lote.correr()
    paths = lote.ctx.paths
    variables = SqlAlchemyConversationalVariableRepository(paths)
    variables.save(ConversationalVariable(project_id=lote.pid, code="campus", label="Campus",
                                          metadata_field_id="campus"))
    intents = SqlAlchemyIntentRepository(paths)
    intents.save(Intent(project_id=lote.pid, name="consultar_requisitos",
                        positive_examples=["requisitos de ingreso certificado acta"], required_variables=["campus"]))
    simulador = SimulateConversation(
        intents, variables, SqlAlchemyGuardrailRuleRepository(paths), SqlAlchemyChannelingSchemeRepository(paths),
        SqlAlchemySourceMetadataRepository(paths), lote.rag, source_repository=SqlAlchemySourceRepository(paths),
        schema_repository=SqlAlchemyMetadataSchemaRepository(paths), catalog_repository=SqlAlchemyCatalogRepository(paths),
    )
    por_plantel = {}
    for plantel in ("hilario_medina", "torres_landa"):
        trace = simulador.execute(lote.pid, "requisitos de ingreso certificado acta", {"campus": plantel}, limit=20)
        por_plantel[plantel] = {r.chunk.source_id for r in trace.search_results}
    for plantel, ajeno in (("hilario_medina", "programa_tl"), ("torres_landa", "programa_hm")):
        assert lote.ids["requisitos_ingreso"] in por_plantel[plantel]
        assert lote.ids[ajeno] not in por_plantel[plantel]
