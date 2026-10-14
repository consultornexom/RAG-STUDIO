"""Pruebas unitarias de SimulateConversation (Etapa 5, el Simulador que
conecta intenciones/variables/guardrails/canalización con el motor RAG
de Etapa 4)."""
from domain.conversational.entities import (
    ChannelingScheme, ConversationalVariable, GuardrailRule, Intent, IntentResolutionMode, RuleActionType,
    RuleType,
)
from domain.documents.entities import Source, SourceType
from domain.ingestion.entities import Chunk, ChunkType
from domain.metadata.entities import SourceMetadataValue
from domain.rag.entities import VectorPoint

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryChunkRepository
from .fakes_metadata import InMemorySourceMetadataRepository
from .fakes_rag import (
    FakeImageEmbeddingProvider, FakeReranker, FakeVectorStore, InMemoryIndexInfoRepository,
    WordOverlapFakeEmbeddingProvider,
)
from application.rag.service import RagService
from application.conversational.queries.simulate_conversation import SimulateConversation


def _index_chunk(chunk_repo, embedder, store, project_id, chunk: Chunk) -> None:
    chunk_repo.save_many(project_id, [chunk])
    [vector] = embedder.embed_texts([chunk.text])
    store.ensure_collection(project_id, embedder.dimensions)
    store.upsert(project_id, [VectorPoint(id=chunk.id, vector=vector, payload={"source_id": chunk.source_id})])


class Fixture:
    def __init__(self):
        self.intents = InMemoryIntentRepository()
        self.variables = InMemoryConversationalVariableRepository()
        self.guardrails = InMemoryGuardrailRuleRepository()
        self.channeling = InMemoryChannelingSchemeRepository()
        self.source_metadata = InMemorySourceMetadataRepository()
        self.sources = InMemorySourceRepository()
        self.chunks = InMemoryChunkRepository()
        # WordOverlapFakeEmbeddingProvider (no FakeEmbeddingProvider):
        # SimulateConversation ahora también usa el proveedor de
        # embeddings para emparejamiento semántico de intención (ver
        # domain.conversational.intent_matching), y el ruido puramente
        # hash-based de FakeEmbeddingProvider produce coincidencias
        # falsas ahí -- ver el docstring de WordOverlapFakeEmbeddingProvider.
        self.embedder = WordOverlapFakeEmbeddingProvider()
        self.store = FakeVectorStore()
        self.rag = RagService(
            self.chunks, self.embedder, self.store, InMemoryIndexInfoRepository(),
            source_repository=self.sources,
        )
        self.simulate = SimulateConversation(
            self.intents, self.variables, self.guardrails, self.channeling, self.source_metadata, self.rag,
        )

    def add_validated_source_with_chunk(self, source_id: str, text: str, **source_kwargs) -> Source:
        source = Source(
            id=source_id, project_id="p1", title=f"Fuente {source_id}", source_type=SourceType.TXT,
            validation_status="validado", **source_kwargs,
        )
        self.sources.save(source)
        chunk = Chunk(project_id="p1", source_id=source_id, chunk_index=0, text=text, token_count=len(text.split()))
        _index_chunk(self.chunks, self.embedder, self.store, "p1", chunk)
        return source

    def add_validated_source_with_structured_rows(
        self, source_id: str, rows: list[dict], section_title: str = "datos", **source_kwargs,
    ) -> Source:
        """Pista B.4 del ADR-003: una fuente con un bloque ya fragmentado
        como ChunkType.ESTRUCTURADO (ver B.2b) -- deliberadamente sin
        pasar por _index_chunk/FakeVectorStore, porque RagService.
        query_structured (application/rag/queries/structured_query.py)
        lee directamente de ChunkRepository, nunca del índice vectorial.

        **source_kwargs (auditoría posterior a la Ronda 76): permite
        fijar access_level/validation_status distintos del default de
        esta fábrica -- ver las pruebas de only_usable_sources/
        max_access_level sobre la vía ESTRUCTURADA, más abajo."""
        source_kwargs.setdefault("validation_status", "validado")
        source = Source(
            id=source_id, project_id="p1", title=f"Fuente {source_id}", source_type=SourceType.XLSX,
            **source_kwargs,
        )
        self.sources.save(source)
        chunk = Chunk(
            project_id="p1", source_id=source_id, chunk_index=0, text=section_title, token_count=1,
            chunk_type=ChunkType.ESTRUCTURADO, section_title=section_title,
            structured_content={"filas": rows},
        )
        self.chunks.save_many("p1", [chunk])
        return source


def test_simulate_responds_directly_when_intent_matches_with_no_guardrail_or_missing_data():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito para ingresar")

    assert trace.matched_intent_name == "Consultar requisitos"
    assert trace.action == RuleActionType.RESPONDER
    assert trace.missing_variables == []
    assert len(trace.search_results) == 1
    assert trace.search_results[0].chunk.source_id == "s1"


def test_simulate_asks_for_clarification_when_a_required_variable_is_missing():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
        required_variables=["programa"], clarifying_questions={"programa": "¿De qué programa?"},
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito", provided_variables={})

    assert trace.action == RuleActionType.ACLARAR
    assert trace.missing_variables == ["programa"]
    assert trace.clarifying_question == "¿De qué programa?"
    assert trace.search_results == []  # nunca busca si todavía falta un dato mínimo


def test_simulate_does_not_ask_for_clarification_when_the_required_variable_is_provided():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
        required_variables=["programa"], clarifying_questions={"programa": "¿De qué programa?"},
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito", provided_variables={"programa": "Ingeniería"})

    assert trace.action == RuleActionType.RESPONDER
    assert trace.missing_variables == []


def test_simulate_abstains_when_no_intent_matches():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Consultar horarios", positive_examples=["a qué hora abren"]))

    trace = fx.simulate.execute("p1", "quiero cancelar mi tarjeta de crédito")

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.matched_intent_name is None
    assert trace.abstention_reason is not None
    assert trace.search_results == []


def test_simulate_channels_when_a_guardrail_rule_fires_and_resolves_the_fallback_scheme():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "información sobre trámites de baja")
    fx.intents.save(Intent(
        project_id="p1", name="Dar de baja", positive_examples=["quiero darme de baja"],
        fallback_channeling_code="soporte-humano",
    ))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Riesgo alto siempre se canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[], action=RuleActionType.CANALIZAR,
    ))
    fx.channeling.save(ChannelingScheme(
        project_id="p1", code="soporte-humano", name="Soporte humano", medium="ticket",
        user_message="Un asesor te contactará en breve.",
    ))

    trace = fx.simulate.execute("p1", "quiero darme de baja")

    assert trace.action == RuleActionType.CANALIZAR
    assert trace.fired_rules == ["Riesgo alto siempre se canaliza"]
    assert trace.channeling is not None
    assert trace.channeling.code == "soporte-humano"
    assert trace.search_results == []  # canalizar nunca llega a buscar


def test_simulate_channels_without_package_when_the_fallback_scheme_was_deactivated():
    # Auditoria profunda (ronda posterior a la 76, ver bitacora):
    # get_by_code() no filtraba por `active` -- un ChannelingScheme
    # desactivado (p. ej. porque el buzon/webhook de destino ya no
    # existe) seguia canalizandose de verdad, a diferencia de una
    # Intent o una GuardrailRule desactivadas (que sí dejan de
    # aplicarse). Mismo criterio "desactivar, nunca borrar" para los
    # tres mecanismos.
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "información sobre trámites de baja")
    fx.intents.save(Intent(
        project_id="p1", name="Dar de baja", positive_examples=["quiero darme de baja"],
        fallback_channeling_code="soporte-humano",
    ))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Riesgo alto siempre se canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[], action=RuleActionType.CANALIZAR,
    ))
    fx.channeling.save(ChannelingScheme(
        project_id="p1", code="soporte-humano", name="Soporte humano", medium="ticket",
        user_message="Un asesor te contactará en breve.", active=False,
    ))

    trace = fx.simulate.execute("p1", "quiero darme de baja")

    assert trace.action == RuleActionType.CANALIZAR
    assert trace.channeling is None


def test_simulate_channels_without_package_when_intent_has_no_fallback_scheme_configured():
    fx = Fixture()
    fx.intents.save(Intent(project_id="p1", name="Dar de baja", positive_examples=["quiero darme de baja"]))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Siempre canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[], action=RuleActionType.CANALIZAR,
    ))

    trace = fx.simulate.execute("p1", "quiero darme de baja")

    assert trace.action == RuleActionType.CANALIZAR
    assert trace.channeling is None


def test_simulate_filters_results_by_conversational_variable_linked_to_metadata_field():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s-ingenieria", "requisitos generales del programa de ingeniería")
    fx.add_validated_source_with_chunk("s-derecho", "requisitos generales del programa de derecho")
    fx.source_metadata.save_value("p1", SourceMetadataValue(source_id="s-ingenieria", field_id="f-programa", value="Ingeniería"))
    fx.source_metadata.save_value("p1", SourceMetadataValue(source_id="s-derecho", field_id="f-programa", value="Derecho"))
    fx.variables.save(ConversationalVariable(project_id="p1", code="programa", label="Programa", metadata_field_id="f-programa"))
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos", positive_examples=["requisitos generales del programa"],
        optional_variables=["programa"],
    ))

    trace = fx.simulate.execute(
        "p1", "requisitos generales del programa", provided_variables={"programa": "Ingeniería"}, limit=10,
    )

    assert trace.action == RuleActionType.RESPONDER
    assert trace.applied_metadata_filters == {"programa": "Ingeniería"}
    assert all(r.chunk.source_id == "s-ingenieria" for r in trace.search_results)
    assert trace.excluded_by_metadata_filter >= 1


def test_simulate_abstains_when_metadata_filter_excludes_every_result():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s-derecho", "requisitos generales del programa de derecho")
    fx.source_metadata.save_value("p1", SourceMetadataValue(source_id="s-derecho", field_id="f-programa", value="Derecho"))
    fx.variables.save(ConversationalVariable(project_id="p1", code="programa", label="Programa", metadata_field_id="f-programa"))
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos", positive_examples=["requisitos generales del programa"],
        optional_variables=["programa"],
    ))

    trace = fx.simulate.execute(
        "p1", "requisitos generales del programa", provided_variables={"programa": "Medicina"}, limit=10,
    )

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.search_results == []
    assert trace.abstention_reason is not None


def test_simulate_never_returns_a_source_that_is_not_validated_even_when_rag_lab_would():
    fx = Fixture()
    # Fuente en borrador -- el Laboratorio RAG (Etapa 4) sí la mostraría
    # por defecto (only_usable_sources=False), pero un motor
    # conversacional real nunca debe hacerlo (documento maestro,
    # "supuestos prohibidos"; ver README limitaciones Etapa 4).
    source = Source(id="s-borrador", project_id="p1", title="Borrador", source_type=SourceType.TXT, validation_status="borrador")
    fx.sources.save(source)
    chunk = Chunk(project_id="p1", source_id="s-borrador", chunk_index=0, text="requisitos generales todavía sin validar", token_count=5)
    _index_chunk(fx.chunks, fx.embedder, fx.store, "p1", chunk)
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos generales"]))

    trace = fx.simulate.execute("p1", "requisitos generales")

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.search_results == []


def test_simulate_reports_fired_rule_names_even_when_final_action_is_forced_by_missing_data():
    fx = Fixture()
    fx.add_validated_source_with_chunk("s1", "información general")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar información", positive_examples=["información general"],
        required_variables=["programa"],
    ))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Siempre pide aclaración", rule_type=RuleType.ACLARACION,
        conditions=[], action=RuleActionType.ACLARAR,
    ))

    trace = fx.simulate.execute("p1", "información general")

    assert trace.action == RuleActionType.ACLARAR
    assert trace.fired_rules == ["Siempre pide aclaración"]


# ---------- Pista B.4 del ADR-003: enrutamiento multi-índice determinista ----------

def test_simulate_resolves_via_structured_query_when_intent_is_estructurado_and_finds_rows():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows(
        "s-costos", [{"plantel": "Campus Norte", "costo": "1500"}, {"plantel": "Campus Sur", "costo": "1800"}],
    )
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    trace = fx.simulate.execute("p1", "cuánto cuesta la colegiatura")

    assert trace.action == RuleActionType.RESPONDER
    assert trace.structured_result is not None
    assert len(trace.structured_result.rows) == 2
    assert trace.search_results == []  # Opción B: un único camino ganador, nunca ambos mezclados


def test_simulate_derives_equality_filter_from_a_provided_variable_bound_to_a_structured_column():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows(
        "s-costos", [{"plantel": "Campus Norte", "costo": "1500"}, {"plantel": "Campus Sur", "costo": "1800"}],
    )
    fx.variables.save(ConversationalVariable(
        project_id="p1", code="plantel", label="Plantel", structured_column="plantel",
    ))
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        optional_variables=["plantel"], resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    trace = fx.simulate.execute(
        "p1", "cuánto cuesta la colegiatura", provided_variables={"plantel": "Campus Sur"},
    )

    assert trace.structured_result is not None
    assert [row.values["plantel"] for row in trace.structured_result.rows] == ["Campus Sur"]


def test_simulate_falls_back_to_semantic_search_when_structured_query_finds_nothing():
    fx = Fixture()
    # Ninguna fuente con bloque ESTRUCTURADO -- solo una fuente de texto
    # normal, para confirmar la degradación automática (sección 4.3 del
    # documento de diseño de B.4): marcar una intención como
    # ESTRUCTURADO nunca debe dejarla peor que si hubiera quedado en
    # SEMANTICO.
    fx.add_validated_source_with_chunk("s1", "la colegiatura cuesta mil quinientos pesos")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    trace = fx.simulate.execute("p1", "cuánto cuesta la colegiatura")

    assert trace.action == RuleActionType.RESPONDER
    assert trace.structured_result is None
    assert len(trace.search_results) == 1
    assert trace.search_results[0].chunk.source_id == "s1"


def test_simulate_abstains_mentioning_the_structured_attempt_when_both_paths_find_nothing():
    fx = Fixture()
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    trace = fx.simulate.execute("p1", "cuánto cuesta la colegiatura")

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.structured_result is None
    assert "estructurada" in trace.abstention_reason


# ---------- vía ESTRUCTURADA y control de acceso (auditoria profunda
# posterior a la Ronda 76 -- ver bitacora: SimulateConversation._query_structured
# nunca aplicaba only_usable_sources/max_access_level, a diferencia de
# _search_and_filter (la via SEMANTICA), pese a que ambas atienden la
# misma conversacion real -- incluida la de un WidgetToken publico) ----------

def test_simulate_structured_query_excludes_rows_above_the_channel_access_ceiling():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows(
        "s-costos", [{"plantel": "Campus Norte", "costo": "1500"}],
        access_level="confidencial",
    )
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    # Mismo techo de acceso que emitiría un WidgetToken público (Pista
    # B.3) -- la única fuente con datos estructurados es CONFIDENCIAL,
    # así que la vía estructurada no debe encontrar nada, y el motor
    # degrada a búsqueda semántica (que tampoco tiene nada) y se
    # abstiene, en vez de filtrar un costo que esa fuente no autoriza.
    trace = fx.simulate.execute(
        "p1", "cuánto cuesta la colegiatura", max_access_level="publico",
    )

    assert trace.structured_result is None
    assert trace.action == RuleActionType.ABSTENERSE


def test_simulate_structured_query_keeps_rows_within_the_channel_access_ceiling():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows(
        "s-costos", [{"plantel": "Campus Norte", "costo": "1500"}],
        access_level="publico",
    )
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    trace = fx.simulate.execute(
        "p1", "cuánto cuesta la colegiatura", max_access_level="publico",
    )

    assert trace.structured_result is not None
    assert len(trace.structured_result.rows) == 1


def test_simulate_structured_query_excludes_rows_from_a_source_not_yet_validated():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows(
        "s-costos", [{"plantel": "Campus Norte", "costo": "1500"}],
        validation_status="borrador",
    )
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    ))

    # only_usable_sources=True es forzado siempre en la vía
    # ESTRUCTURADA (igual que en la SEMANTICA) -- una fuente en
    # "borrador" no es usable para responder, con o sin techo de acceso.
    trace = fx.simulate.execute("p1", "cuánto cuesta la colegiatura")

    assert trace.structured_result is None
    assert trace.action == RuleActionType.ABSTENERSE


def test_simulate_uses_semantic_search_directly_when_intent_is_semantico_even_with_structured_data_present():
    fx = Fixture()
    fx.add_validated_source_with_structured_rows("s-costos", [{"plantel": "Campus Norte", "costo": "1500"}])
    fx.intents.save(Intent(
        project_id="p1", name="Consultar costos", positive_examples=["cuánto cuesta la colegiatura"],
        # resolution_mode por defecto -- SEMANTICO, ver domain.conversational.entities.Intent.
    ))

    trace = fx.simulate.execute("p1", "cuánto cuesta la colegiatura")

    assert trace.structured_result is None


# Ronda 40 (cierre de la Opción 1 de C.4 del ADR-003): SimulateConversation
# -- el motor conversacional real, tanto del Simulador de escritorio como
# de POST /projects/{id}/messages -- ahora pide rerank=True a
# RagService.search_hybrid cuando el RagService con el que se construyó
# tiene un Reranker real configurado (RagService.has_reranker), en vez de
# nunca pedirlo como antes de esta ronda.
class FixtureWithReranker(Fixture):
    def __init__(self):
        self.intents = InMemoryIntentRepository()
        self.variables = InMemoryConversationalVariableRepository()
        self.guardrails = InMemoryGuardrailRuleRepository()
        self.channeling = InMemoryChannelingSchemeRepository()
        self.source_metadata = InMemorySourceMetadataRepository()
        self.sources = InMemorySourceRepository()
        self.chunks = InMemoryChunkRepository()
        self.embedder = WordOverlapFakeEmbeddingProvider()
        self.store = FakeVectorStore()
        self.reranker = FakeReranker()
        self.rag = RagService(
            self.chunks, self.embedder, self.store, InMemoryIndexInfoRepository(),
            source_repository=self.sources, reranker=self.reranker,
        )
        self.simulate = SimulateConversation(
            self.intents, self.variables, self.guardrails, self.channeling, self.source_metadata, self.rag,
        )


def test_simulate_uses_the_real_reranker_by_default_when_rag_service_has_one_configured():
    fx = FixtureWithReranker()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
    ))

    fx.simulate.execute("p1", "qué requisitos necesito para ingresar")

    # FakeReranker.received_query solo queda asignado si de verdad se
    # invocó -- confirma que SimulateConversation pidió rerank=True sin
    # que se lo pidiera explícitamente quien la llama.
    assert fx.reranker.received_query == "qué requisitos necesito para ingresar"


def test_simulate_does_not_request_rerank_when_rag_service_has_no_reranker_configured():
    fx = Fixture()  # sin reranker -- has_reranker es False, mismo comportamiento que antes de la Ronda 40
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito para ingresar")

    # No lanza RerankerUnavailableError -- rerank=self._rag.has_reranker
    # nunca pide True cuando no hay ningún Reranker configurado.
    assert trace.action == RuleActionType.RESPONDER


# ---------- Cierre del vacío 2 de la Ronda 66 (RAG3 Fase 3): tercer canal
# image_results, ver docstring de SimulationTrace.image_results ----------

class FixtureWithImages(Fixture):
    """Mismo Fixture base, pero con un image_embedding_provider real
    (FakeImageEmbeddingProvider) -- sin él, RagService.has_image_search
    es False y SimulateConversation nunca intenta buscar imágenes (ver
    test_simulate_leaves_image_results_empty_when... más abajo)."""

    def __init__(self):
        super().__init__()
        self.image_embedder = FakeImageEmbeddingProvider()
        self.rag = RagService(
            self.chunks, self.embedder, self.store, InMemoryIndexInfoRepository(),
            source_repository=self.sources, image_embedding_provider=self.image_embedder,
        )
        self.simulate = SimulateConversation(
            self.intents, self.variables, self.guardrails, self.channeling, self.source_metadata, self.rag,
        )

    def add_validated_image_source(self, source_id: str, filename: str, tmp_path) -> Source:
        """Registra e indexa (vía RagService.index_image_source, el
        mismo camino real que usa RunPipeline) una fuente
        IMAGEN_NATIVA -- necesita un archivo real en disco porque
        IndexImageSource lee Source.original_copy_path directamente."""
        path = tmp_path / filename
        path.write_bytes(b"contenido binario cualquiera, no importa para esta prueba")
        source = Source(
            id=source_id, project_id="p1", title=f"Imagen {source_id}", source_type=SourceType.IMAGEN_NATIVA,
            validation_status="validado", location=str(path), original_copy_path=str(path),
        )
        self.sources.save(source)
        self.rag.index_image_source("p1", source_id)
        return source


def test_simulate_populates_image_results_when_responding_and_image_search_is_available(tmp_path):
    fx = FixtureWithImages()
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.add_validated_image_source("s-img", "logo.png", tmp_path)
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito para ingresar")

    assert trace.action == RuleActionType.RESPONDER
    assert len(trace.image_results) == 1
    assert trace.image_results[0].chunk.source_id == "s-img"
    # Nunca se fusiona con el canal de texto (Ronda 36) -- son listas
    # completamente independientes en el mismo trace.
    assert len(trace.search_results) == 1
    assert trace.search_results[0].chunk.source_id == "s1"


def test_simulate_leaves_image_results_empty_when_action_is_not_responder():
    fx = FixtureWithImages()
    fx.intents.save(Intent(project_id="p1", name="Consultar horarios", positive_examples=["a qué hora abren"]))

    trace = fx.simulate.execute("p1", "quiero cancelar mi tarjeta de crédito")

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.image_results == []


def test_simulate_leaves_image_results_empty_when_the_only_evidence_is_an_abstained_text_search():
    # Aunque RagService tenga soporte de imágenes configurado, si el
    # canal de texto no encontró nada utilizable la acción final se
    # degrada a ABSTENERSE ANTES de intentar buscar imágenes -- no debe
    # quedar un image_results poblado "huérfano" para una respuesta que
    # ya no se va a dar (ver comentario en simulate_conversation.py,
    # justo antes de la llamada a search_images).
    fx = FixtureWithImages()
    fx.intents.save(Intent(project_id="p1", name="Consultar requisitos", positive_examples=["requisitos generales"]))

    trace = fx.simulate.execute("p1", "requisitos generales")

    assert trace.action == RuleActionType.ABSTENERSE
    assert trace.image_results == []


def test_simulate_leaves_image_results_empty_when_rag_service_has_no_image_search_configured():
    fx = Fixture()  # sin image_embedding_provider -- has_image_search es False
    fx.add_validated_source_with_chunk("s1", "los requisitos de ingreso son boleta y acta de nacimiento")
    fx.intents.save(Intent(
        project_id="p1", name="Consultar requisitos",
        positive_examples=["qué requisitos necesito", "requisitos de ingreso"],
    ))

    trace = fx.simulate.execute("p1", "qué requisitos necesito para ingresar")

    # No lanza ImageSearchUnavailableError -- mismo criterio de
    # "capacidad opcional" que ya prueba
    # test_simulate_does_not_request_rerank_when...
    assert trace.action == RuleActionType.RESPONDER
    assert trace.image_results == []


# ---------- Ronda 87 (2026-10-02, hallazgo real de usuario sobre Canalización) ----------

def _fixture_que_canaliza(fallback_code, scheme_kwargs=None):
    fx = Fixture()
    fx.intents.save(Intent(
        project_id="p1", name="Solicitar asesor humano", positive_examples=["quiero hablar con un asesor humano"],
        fallback_channeling_code=fallback_code,
    ))
    fx.guardrails.save(GuardrailRule(
        project_id="p1", name="Asesor humano se canaliza", rule_type=RuleType.CANALIZACION,
        conditions=[{"field": "intención", "operator": "=", "value": '"Solicitar asesor humano"'}],
        action=RuleActionType.CANALIZAR,
    ))
    if scheme_kwargs is not None:
        fx.channeling.save(ChannelingScheme(project_id="p1", **scheme_kwargs))
    return fx


def test_condicion_con_acento_y_comillas_dispara_la_canalizacion():
    fx = _fixture_que_canaliza(
        "canal_asesor_humano", {"code": "canal_asesor_humano", "name": "Asesor", "medium": "correo"},
    )
    trace = fx.simulate.execute("p1", "quiero hablar con un asesor humano")
    assert trace.action == RuleActionType.CANALIZAR
    assert trace.channeling is not None and trace.channeling.code == "canal_asesor_humano"
    assert trace.channeling_note is None


def test_nota_cuando_la_intencion_no_tiene_canalizacion_alternativa():
    trace = _fixture_que_canaliza(None).simulate.execute("p1", "quiero hablar con un asesor humano")
    assert trace.channeling is None
    assert "no tiene canalización alternativa" in trace.channeling_note


def test_nota_cuando_el_codigo_no_corresponde_a_ningun_esquema():
    fx = _fixture_que_canaliza("canal_asesor", {"code": "canal_asesor_humano", "name": "Asesor"})
    trace = fx.simulate.execute("p1", "quiero hablar con un asesor humano")
    assert trace.channeling is None
    assert "no existe ningún esquema con ese código" in trace.channeling_note


def test_nota_cuando_el_esquema_esta_inactivo():
    fx = _fixture_que_canaliza(
        "canal_asesor_humano", {"code": "canal_asesor_humano", "name": "Asesor", "active": False},
    )
    trace = fx.simulate.execute("p1", "quiero hablar con un asesor humano")
    assert trace.channeling is None
    assert "inactivo" in trace.channeling_note
