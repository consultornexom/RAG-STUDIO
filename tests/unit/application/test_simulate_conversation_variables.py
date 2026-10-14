"""Ronda 89 (2026-10-04, hallazgo real de usuario en AGENTE UDL): la
consulta nombraba el programa pero la variable quedaba "faltante"; y el
filtro de metadatos se aplicaba DESPUÉS de elegir el top-k global."""
from domain.conversational.entities import ConversationalVariable, Intent, RuleActionType
from domain.documents.entities import Source, SourceType
from domain.ingestion.entities import Chunk
from domain.metadata.entities import Catalog, CatalogEntry, FieldDefinition, MetadataSchema, SourceMetadataValue
from domain.rag.entities import VectorPoint

from application.conversational.queries.simulate_conversation import SimulateConversation
from application.rag.service import RagService

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryChunkRepository
from .fakes_metadata import (
    InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository,
)
from .fakes_rag import FakeVectorStore, InMemoryIndexInfoRepository, WordOverlapFakeEmbeddingProvider

P = "p1"


class Fx:
    def __init__(self, con_repos_nuevos: bool = True):
        self.intents = InMemoryIntentRepository()
        self.variables = InMemoryConversationalVariableRepository()
        self.sources = InMemorySourceRepository()
        self.chunks = InMemoryChunkRepository()
        self.metadata = InMemorySourceMetadataRepository()
        self.schemas = InMemoryMetadataSchemaRepository()
        self.catalogs = InMemoryCatalogRepository()
        self.embedder = WordOverlapFakeEmbeddingProvider()
        self.store = FakeVectorStore()
        rag = RagService(self.chunks, self.embedder, self.store, InMemoryIndexInfoRepository(), source_repository=self.sources)
        extra = dict(source_repository=self.sources, schema_repository=self.schemas, catalog_repository=self.catalogs)
        self.simulate = SimulateConversation(
            self.intents, self.variables, InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
            self.metadata, rag, **(extra if con_repos_nuevos else {}),
        )
        schema = MetadataSchema(project_id=P)
        self.schemas.save_schema(schema)
        catalogo = Catalog(project_id=P, name="Programas")
        self.catalogs.save_catalog(catalogo)
        for code, label in [
            ("gestion_profesional_de_proyectos", "Gestión Profesional de Proyectos"),
            ("derecho_corporativo", "Derecho Corporativo"),
        ]:
            self.catalogs.save_entry(P, CatalogEntry(catalog_id=catalogo.id, value_code=code, label=label))
        self.schemas.save_field(P, FieldDefinition(
            field_id="programa_academico", schema_id=schema.id, display_name="Programa", data_type="seleccion_unica",
            catalog_id=catalogo.id,
        ))
        self.variables.save(ConversationalVariable(
            project_id=P, code="programa_academico", label="Programa", metadata_field_id="programa_academico",
        ))
        self.intents.save(Intent(
            project_id=P, name="Consultar programa específico",
            positive_examples=["cual es el objetivo del programa", "dame informacion del programa"],
            required_variables=["programa_academico"],
        ))

    def fuente(self, source_id: str, programa: str, textos: list[str]) -> None:
        self.sources.save(Source(
            id=source_id, project_id=P, title=source_id, source_type=SourceType.TXT, validation_status="validado",
        ))
        self.metadata.save_value(P, SourceMetadataValue(source_id=source_id, field_id="programa_academico", value=programa))
        for i, texto in enumerate(textos):
            chunk = Chunk(project_id=P, source_id=source_id, chunk_index=i, text=texto, token_count=len(texto.split()))
            self.chunks.save_many(P, [chunk])
            [vector] = self.embedder.embed_texts([texto])
            self.store.ensure_collection(P, self.embedder.dimensions)
            self.store.upsert(P, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": source_id})])


def _escenario(con_repos_nuevos: bool = True) -> Fx:
    fx = Fx(con_repos_nuevos)
    fx.fuente("s-gpp", "gestion_profesional_de_proyectos", [
        "Diplomado de Alta Especialidad en Gestión Profesional de Proyectos",
        "Objetivo: aprender a planificar y cerrar proyectos estratégicos",
    ])
    # Otra fuente con muchos fragmentos que se parecen MÁS a la pregunta:
    # con el filtro posterior al top-k, llenaban los primeros lugares.
    fx.fuente("s-otro", "derecho_corporativo", [
        f"cual es el objetivo del programa objetivo objetivo {i}" for i in range(8)
    ])
    return fx


def test_la_variable_se_detecta_en_el_texto_de_la_consulta():
    fx = _escenario()
    trace = fx.simulate.execute(P, "¿Cuál es el objetivo del programa Gestión Profesional de Proyectos?", limit=2)
    assert trace.detected_variables == {"programa_academico": "gestion_profesional_de_proyectos"}
    assert trace.missing_variables == []
    assert trace.action == RuleActionType.RESPONDER
    assert trace.applied_metadata_filters == {"programa_academico": "gestion_profesional_de_proyectos"}


def test_el_filtro_se_aplica_antes_de_elegir_los_mejores_resultados():
    fx = _escenario()
    trace = fx.simulate.execute(
        P, "¿Cuál es el objetivo del programa?", {"programa_academico": "gestion_profesional_de_proyectos"}, limit=2,
    )
    assert trace.search_results, "con filtro posterior quedaba vacío: el top-2 global era de otra fuente"
    assert {r.chunk.source_id for r in trace.search_results} == {"s-gpp"}
    assert any("Objetivo" in r.chunk.text for r in trace.search_results)


def test_la_busqueda_quita_la_mencion_del_valor_ya_filtrado():
    fx = _escenario()
    trace = fx.simulate.execute(P, "¿Cuál es el objetivo de Gestión Profesional de Proyectos?", limit=2)
    assert trace.retrieval_query == "¿Cuál es el objetivo ?"
    assert any("Objetivo" in r.chunk.text for r in trace.search_results)


def test_lo_proporcionado_explicitamente_tiene_prioridad_sobre_lo_detectado():
    fx = _escenario()
    trace = fx.simulate.execute(
        P, "objetivo de Gestión Profesional de Proyectos", {"programa_academico": "derecho_corporativo"}, limit=2,
    )
    assert trace.detected_variables == {}
    assert trace.applied_metadata_filters == {"programa_academico": "derecho_corporativo"}


def test_campo_de_valor_multiple_coincide_con_cualquiera_de_sus_valores():
    fx = _escenario()
    fx.fuente("s-mixta", "derecho_corporativo|gestion_profesional_de_proyectos", ["Calendario compartido de proyectos"])
    trace = fx.simulate.execute(
        P, "objetivo del programa calendario", {"programa_academico": "gestion_profesional_de_proyectos"}, limit=5,
    )
    assert "s-mixta" in {r.chunk.source_id for r in trace.search_results}


def test_sin_los_repositorios_nuevos_el_comportamiento_es_el_de_antes():
    fx = _escenario(con_repos_nuevos=False)
    trace = fx.simulate.execute(P, "¿Cuál es el objetivo de Gestión Profesional de Proyectos?", limit=2)
    assert trace.detected_variables == {}
    assert trace.missing_variables == ["programa_academico"]


def test_si_ninguna_fuente_tiene_el_valor_filtrado_se_explica():
    fx = _escenario()
    fx.catalogs.save_entry(P, CatalogEntry(
        catalog_id=fx.catalogs.list_catalogs(P)[0].id, value_code="sin_fuente", label="Programa Sin Fuente",
    ))
    trace = fx.simulate.execute(P, "¿Cuál es el objetivo del programa Programa Sin Fuente?", limit=2)
    assert trace.detected_variables == {"programa_academico": "sin_fuente"}
    assert trace.action == RuleActionType.ABSTENERSE
    assert "Ninguna fuente del proyecto tiene asignado programa_academico=sin_fuente" in trace.abstention_reason


def test_pregunta_identica_a_un_ejemplo_con_nombre_de_programa_elige_esa_intencion():
    """Ronda 90 (hallazgo real de usuario): "¿Cuál es el perfil de egreso de
    la licenciatura en Derecho?" era ejemplo positivo de "Consultar perfil
    de egreso", pero ganaba "Consultar programa específico" porque solo la
    consulta perdía el nombre del programa al reconocer la intención."""
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar perfil de egreso", priority=50,
        positive_examples=["¿Cuál es el perfil de egreso de la licenciatura en Gestión Profesional de Proyectos?"],
        negative_examples=["dame informacion del programa"],
        required_variables=["programa_academico"],
    ))
    trace = fx.simulate.execute(
        P, "¿Cuál es el perfil de egreso de la licenciatura en Gestión Profesional de Proyectos?", limit=2,
    )
    assert trace.matched_intent_name == "Consultar perfil de egreso"
    assert trace.confidence == 1.0
    assert trace.detected_variables == {"programa_academico": "gestion_profesional_de_proyectos"}
    assert trace.intent_scores[0].intent_name == "Consultar perfil de egreso"
    assert len(trace.intent_scores) == 2


def test_con_filtro_se_ponen_primero_las_secciones_afines_a_la_intencion():
    """Ronda 91 (hallazgo real de usuario): con intención y programa
    correctos, "Perfil del egresado" quedaba detrás de fragmentos de control
    como "Casos que requieren handoff"."""
    fx = _escenario()
    fx.intents.save(Intent(
        project_id=P, name="Consultar perfil de egreso", description="Consulta el perfil de egreso.",
        positive_examples=["¿Qué conocimientos obtiene quien termina Gestión Profesional de Proyectos?"],
        required_variables=["programa_academico"],
    ))
    fx.fuente("s-gpp2", "gestion_profesional_de_proyectos", [])
    for i, (titulo, texto) in enumerate([
        ("Casos que requieren handoff", "conocimientos obtiene quien termina canalizar"),
        ("Perfil del egresado", "Al terminar domina la gestión de proyectos"),
    ]):
        from domain.ingestion.entities import Chunk
        from domain.rag.entities import VectorPoint
        chunk = Chunk(project_id=P, source_id="s-gpp", chunk_index=10 + i, text=texto, token_count=5, section_title=titulo)
        fx.chunks.save_many(P, [chunk])
        [vector] = fx.embedder.embed_texts([texto])
        fx.store.upsert(P, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": "s-gpp"})])
    trace = fx.simulate.execute(
        P, "¿Qué conocimientos obtiene quien termina la licenciatura en Gestión Profesional de Proyectos?", limit=3,
    )
    assert trace.matched_intent_name == "Consultar perfil de egreso"
    assert trace.section_ordering is True
    assert trace.search_results[0].chunk.section_title == "Perfil del egresado"
