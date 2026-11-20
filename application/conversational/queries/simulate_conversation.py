"""El Simulador (Etapa 5, "Diseño conversacional" -- RAG STUDIO.odt:
"Debe permitir probar el agente sin publicarlo (...) Muestra por qué se
generó la respuesta. Esto es fundamental para depurar errores sin
limitarse a observar el texto final.").

`SimulateConversation` es la pieza central que conecta todo lo demás de
Etapa 5 con el motor RAG de Etapa 4: dada una consulta (y, opcionalmente,
variables ya proporcionadas por la persona que prueba el agente, como si
fueran datos que el usuario real ya dio en la conversación), decide si
el agente puede responder, debe aclarar, debe abstenerse o debe
canalizar -- y solo busca en el índice cuando de verdad va a responder.

El reporte que produce (SimulationTrace) sigue el listado exacto que
pide el documento maestro para el simulador: "Intención. Confianza.
Variables detectadas. Datos faltantes. Pregunta aclaratoria. Filtros.
Fuentes. Fragmentos. Reglas activadas. Decisión tomada. Canalización."
"""
from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel, Field

from application.rag.queries.semantic_search import SemanticSearchResult
from application.rag.queries.semantic_search_images import ImageSearchResult
from application.rag.service import RagService
from domain.conversational.entities import (
    ACTION_SEVERITY, ChannelingScheme, Intent, IntentResolutionMode, RuleActionType,
)
from domain.conversational.intent_matching import match_intent
from domain.conversational.ports import (
    ChannelingSchemeRepository, ConversationalVariableRepository, GuardrailRuleRepository, IntentRepository,
)
from domain.conversational.rule_evaluation import select_firing_action
from domain.documents.entities import AccessLevel
from domain.conversational.reference_resolution import enforce_destinations_first, resolve_references
from domain.conversational.retrieval_procedure import (
    DEFAULT_FOR_NEW_PROJECTS, PROCEDURE_R106, SUPPORTED_PROCEDURES, validate_procedure,
)
from domain.conversational.section_affinity import (
    SectionAffinity, affinity_title, combine_by_value, combine_with_retrieval,
)
from domain.conversational.variable_extraction import (
    ValueCandidate, alias_forms, extract_variable_values, find_mentions, remove_spans,
)
from domain.documents.ports import SourceRepository
from domain.metadata.ports import CatalogRepository, MetadataSchemaRepository, SourceMetadataRepository
from domain.rag.structured_query import StructuredFilter, StructuredFilterOperator, StructuredQueryResult


def _section_title(chunk, source_title: Optional[str] = None, exclude_yaml_only: bool = False) -> str:
    """Título con el que se mide la afinidad del fragmento (Ronda 102, C2):
    su título de sección; si la fragmentación no lo guardó, su primer
    encabezado Markdown (fuera del encabezado YAML) y, si tampoco hay, el
    título de la fuente. Antes era la primera línea del texto ("---" en
    los documentos con encabezado YAML). exclude_yaml_only: componente Y
    del procedimiento r106 (Ronda 106)."""
    return affinity_title(chunk.section_title, chunk.text, source_title, exclude_yaml_only=exclude_yaml_only)


class IntentScoreView(BaseModel):
    """Ronda 90: vista de domain.conversational.intent_matching.IntentScore
    para el reporte del Simulador."""

    intent_name: str
    margin: float
    positive: float
    negative: float
    priority: int


class ResultOrderingView(BaseModel):
    """Ronda 102: de dónde salió la posición de cada fragmento entregado
    (mismo orden que SimulationTrace.search_results), para separar la
    recuperación inicial del reordenamiento conversacional."""

    retrieval_rank: int
    """Puesto del fragmento en la recuperación inicial (búsqueda híbrida,
    con o sin reranking, dentro de las fuentes permitidas)."""
    affinity: float
    """Afinidad título-intención (0 a 1)."""
    affinity_title: str
    """Título con el que se midió la afinidad (ver _section_title)."""
    referenced_from: list[str] = Field(default_factory=list)
    """Ronda 106 (r106, componente R): chunk_ids de los fragmentos puente que
    remiten a la fuente de este fragmento y lo pusieron por delante de ellos.
    Vacía si el fragmento no llegó por referencia."""
    referenced_from_sources: list[str] = Field(default_factory=list)
    """Ronda 106: títulos de las fuentes de esos fragmentos puente."""


RETRIEVAL_PIPELINE = DEFAULT_FOR_NEW_PROJECTS
"""Desde la Ronda 106, el procedimiento lo elige cada proyecto (ver
domain.conversational.retrieval_procedure): esta constante es el
predeterminado para proyectos NUEVOS ("r106"); el efectivo de cada
consulta está en SimulationTrace.retrieval_pipeline.

Ronda 104b (Etapa 0): identificador del procedimiento de recuperación del
motor conversacional. Cambia cada vez que una ronda altera cómo se ordenan
los fragmentos, para que un trace diga con qué procedimiento se produjo:
- "r102": búsqueda híbrida (RRF semántica + BM25 + señal jerárquica de la
  Ronda 100, conflicto de ordinal de la Ronda 101), reranking según el ajuste
  del proyecto (Ronda 102, C4), filtro de metadatos previo y afinidad
  título-intención combinada por RRF con el puesto de la búsqueda (C1) con
  títulos de C2.
- "r105b": igual que "r102", con la configuración efectiva de reranking de
  la Ronda 105b (P1, alternativa B estricta): Automático y Desactivado =
  sin reranking en el Simulador y en el Runtime; Activado = con reranking,
  exigiendo el modelo cargado (error explícito si no). Para proyectos sin
  «Activado», el orden del Runtime es idéntico al de "r102".
- "r106" (Ronda 106, autorizado por NEXOM): igual que "r105b" con V + Y + R
  en el reordenamiento conversacional (solo con filtro de metadatos): afinidad
  ponderada por valor, sin afinidad para fragmentos solo-YAML y resolución de
  referencias de fragmentos puente. Reranking (P1) sin cambios."""

RETRIEVAL_PIPELINES_SUPPORTED = SUPPORTED_PROCEDURES

RERANKING_AUTOMATICO = "automatico"
RERANKING_ACTIVADO = "activado"
RERANKING_DESACTIVADO = "desactivado"


class SimulationTrace(BaseModel):
    """Resultado completo de una simulación -- pensado para mostrarse
    tal cual en la UI, sin que la interfaz tenga que recalcular nada."""

    model_config = {"arbitrary_types_allowed": True}

    query_text: str
    provided_variables: dict[str, str] = Field(default_factory=dict)
    matched_intent_name: Optional[str] = None
    confidence: float = 0.0
    required_variables: list[str] = Field(default_factory=list)
    missing_variables: list[str] = Field(default_factory=list)
    clarifying_question: Optional[str] = None
    fired_rules: list[str] = Field(default_factory=list)
    action: RuleActionType = RuleActionType.ABSTENERSE
    channeling: Optional[ChannelingScheme] = None
    channeling_note: Optional[str] = None
    """Ronda 87: cuando la decisión es Canalizar pero no hay paquete,
    explica cuál de las tres causas se dio (la intención no tiene
    canalización alternativa; el código no corresponde a ningún esquema;
    el esquema está inactivo). Antes el Simulador mostraba siempre el
    mismo mensaje, que solo describía la primera causa."""
    detected_variables: dict[str, str] = Field(default_factory=dict)
    """Ronda 89: variables que el motor reconoció en el TEXTO de la
    consulta (p. ej. el nombre de un programa del catálogo), además de
    las que vinieron en provided_variables. Se muestran en el Simulador
    para que quien prueba vea de dónde salió cada filtro."""
    ambiguous_variables: dict[str, list[str]] = Field(default_factory=dict)
    """Ronda 89: variables con varias coincidencias igual de específicas
    en la consulta -- no se llenan (se pide aclaración)."""
    section_ordering: bool = False
    """Ronda 91: True si los fragmentos se ordenaron poniendo primero las
    secciones afines a la intención (ver domain.conversational.
    section_affinity). Solo ocurre con filtro de metadatos aplicado, es
    decir, cuando todos los candidatos son de la(s) fuente(s) del valor
    filtrado."""
    intent_scores: list["IntentScoreView"] = Field(default_factory=list)
    """Ronda 90: puntuación de cada intención activa (mayor margen primero),
    para que el Simulador explique por qué ganó una y no otra."""
    retrieval_query: Optional[str] = None
    """Ronda 89: texto realmente usado para buscar fragmentos cuando
    difiere de la consulta (se quitan las menciones de los valores que ya
    se aplicaron como filtro). None si se buscó con la consulta tal cual."""
    applied_metadata_filters: dict[str, str] = Field(default_factory=dict)
    excluded_by_metadata_filter: int = 0
    """Desde la Ronda 89 (filtro previo a la búsqueda): cuántas FUENTES del
    proyecto quedaron fuera por los filtros de metadatos. Antes contaba
    resultados descartados después del top-k; solo vuelve a ese sentido
    si el caso de uso se construye sin repositorio de fuentes."""
    search_results: list[SemanticSearchResult] = Field(default_factory=list)
    result_ordering: list[ResultOrderingView] = Field(default_factory=list)
    """Ronda 102: puesto en la recuperación inicial y afinidad de cada
    fragmento de search_results (vacía si no hubo reordenamiento por
    afinidad)."""
    reranking_setting: str = RERANKING_AUTOMATICO
    """Ronda 102 (C4): ajuste "Reranking en el agente" del proyecto:
    automatico (predeterminado: se aplica si hay modelo instalado),
    activado o desactivado."""
    reranking_applied: bool = False
    """Ronda 102 (C4): True si la búsqueda de esta consulta usó el
    modelo de reranking."""
    reranking_model: Optional[str] = None
    """Ronda 102 (C4): modelo de reranking que intervino (None si no se
    aplicó)."""
    reranking_available: bool = False
    """Ronda 104b (Etapa 0); desde la Ronda 105b (P1): True solo si el modelo
    de reranking está CARGADO y verificado en este proceso (no basta con que
    esté configurado)."""
    reranking_model_status: str = "no_requerido"
    """Ronda 105b (P1): "no_requerido" (Automático/Desactivado: no se
    necesita ni se carga el modelo) o "cargado" (Activado: verificado antes
    de buscar). Si el modelo no carga, no hay trazado: la consulta falla con
    un error explícito."""
    runtime_effective_reranking: str = "sin_reranking"
    """Ronda 105b (P1): configuración efectiva que aplicará el Runtime para
    este proyecto -- la misma del Simulador por construcción: "sin_reranking"
    o "con_reranking" (en el Runtime exige el modelo en el servidor; si no
    lo tiene, el Runtime rechaza servir el proyecto)."""
    reranking_available_model: Optional[str] = None
    retrieval_pipeline: str = "r105b"
    """Ronda 104b (Etapa 0): procedimiento con que se produjo esta traza.
    Desde la Ronda 106 es el ajuste del proyecto ("r105b" o "r106"), el mismo
    en el Simulador y en el Runtime (ver RETRIEVAL_PIPELINE)."""
    ambiguous_references: list[str] = Field(default_factory=list)
    """Ronda 106 (r106, componente R): nombres de fuente mencionados por
    fragmentos puente que corresponden a más de una fuente (no se resuelven)."""
    search_text: Optional[str] = None
    """Ronda 104b (Etapa 0): texto EXACTO con el que se buscó (la consulta
    o, con filtros, retrieval_query). None si no hubo búsqueda de texto."""
    reranking_note: Optional[str] = None
    """Ronda 102 (C4): aviso cuando el ajuste pide reranking y no hay
    modelo instalado."""
    abstention_reason: Optional[str] = None
    structured_result: Optional[StructuredQueryResult] = None
    """Pista B.4 del ADR-003 (enrutamiento multi-índice determinista):
    solo se puebla cuando la intención resuelta tenía resolution_mode
    == ESTRUCTURADO y RagService.query_structured encontró al menos una
    fila -- ver _query_structured. None en cualquier otro caso,
    incluida una intención ESTRUCTURADO que no encontró nada (ese caso
    degrada a search_results, ver execute)."""
    image_results: list[ImageSearchResult] = Field(default_factory=list)
    """Fase 3/4 de multimodalidad nativa (RAG 3): un TERCER canal de
    evidencia, independiente de search_results/structured_result --
    nunca se fusiona con ninguno de los dos (espacios vectoriales no
    comparables, riesgo señalado desde la Ronda 36). Solo se intenta
    poblar cuando la acción final es RESPONDER (ver execute) y
    RagService.has_image_search es True -- lista vacía en cualquier
    otro caso (proyecto sin soporte de imágenes configurado, o
    ninguna imagen relevante encontrada; ambos casos se ven iguales
    aquí, a propósito, mismo criterio que el resto de listas de este
    modelo)."""


class SimulateConversation:
    def __init__(
        self,
        intent_repository: IntentRepository,
        variable_repository: ConversationalVariableRepository,
        guardrail_repository: GuardrailRuleRepository,
        channeling_repository: ChannelingSchemeRepository,
        source_metadata_repository: SourceMetadataRepository,
        rag_service: RagService,
        *,
        source_repository: Optional[SourceRepository] = None,
        schema_repository: Optional[MetadataSchemaRepository] = None,
        catalog_repository: Optional[CatalogRepository] = None,
        agent_reranking: Optional[Callable[[str], Optional[bool]]] = None,
        retrieval_procedure: Optional[Callable[[str], Optional[str]]] = None,
    ):
        """source_repository/schema_repository/catalog_repository (Ronda
        89, opcionales para no romper a quien construya este caso de uso
        sin ellos): habilitan detectar valores de variables en el texto de
        la consulta usando los catálogos y valores de metadatos del
        proyecto, y filtrar por metadatos ANTES de elegir los mejores
        fragmentos. Sin ellos, el comportamiento es el de antes.

        agent_reranking (Ronda 102, C4): devuelve el ajuste "Reranking en
        el agente" del proyecto (None = automático, True = activado,
        False = desactivado). Sin él, automático: el comportamiento de
        siempre (se aplica si RagService tiene modelo de reranking).

        retrieval_procedure (Ronda 106): devuelve el procedimiento guardado
        del proyecto ("r105b", "r106" o None = sin ajuste -> "r105b"). El
        Simulador de escritorio lo lee del project.db en edición y el Runtime
        del project.db de la instantánea servida: el mismo lector y el mismo
        código, por lo que ambos aplican el mismo procedimiento. Sin él,
        "r105b" (comportamiento anterior)."""
        self._agent_reranking = agent_reranking
        self._retrieval_procedure = retrieval_procedure
        self._sources = source_repository
        self._schemas = schema_repository
        self._catalogs = catalog_repository
        # Ronda 91 (auditoría de rendimiento): los vectores de los textos
        # de referencia de las intenciones (ejemplos, nombre, descripción)
        # se recalculaban en CADA consulta (~100 textos, ~2 s). Cambian
        # rara vez, así que se guardan en memoria por texto exacto; un
        # ejemplo editado es un texto distinto y se calcula de nuevo.
        self._reference_vectors: dict[str, list[float]] = {}
        self._intents = intent_repository
        self._variables = variable_repository
        self._guardrails = guardrail_repository
        self._channeling = channeling_repository
        self._source_metadata = source_metadata_repository
        self._rag = rag_service

    def execute(
        self, project_id: str, query_text: str, provided_variables: Optional[dict[str, str]] = None,
        source_id: Optional[str] = None, limit: int = 5,
        max_access_level: Optional[AccessLevel] = None,
    ) -> SimulationTrace:
        """max_access_level (Pista B.3 del ADR-003): techo de acceso del
        canal que hace esta consulta -- None (default) significa sin
        techo, mismo comportamiento de siempre. `HandleIncomingMessage`
        (el camino real de POST /messages) lo resuelve a partir del
        WidgetToken/API key que autenticó la solicitud; el Simulador de
        escritorio (ui/conversational/panel.py) nunca lo pasa, porque
        ahí quien prueba el agente ya tiene acceso completo al
        proyecto."""
        provided = dict(provided_variables or {})
        procedure = self._procedure_decision(project_id)
        intents = self._intents.list_for_project(project_id)
        # embed_query/embed_texts reutilizan el mismo EmbeddingProvider
        # de RagService (Etapa 4) para emparejamiento semántico de
        # intención, además del heurístico léxico -- ver
        # domain.conversational.intent_matching para el porqué (tolera
        # paráfrasis/sinónimos, se degrada solo a léxico sin red).
        # Ronda 89: para reconocer la intención se quitan de la consulta
        # las menciones de valores de catálogo (p. ej. el nombre del
        # programa). Esas palabras dicen DE QUÉ programa se pregunta, no
        # QUÉ se pregunta, y como cada ejemplo de intención nombra un
        # programa distinto, solo agregaban ruido a la similitud.
        #
        # Ronda 90 (hallazgo real de usuario): la misma transformación se
        # aplica a los ejemplos de las intenciones (text_transform), no
        # solo a la consulta. Con la consulta enmascarada y los ejemplos
        # intactos, una pregunta idéntica a un ejemplo positivo dejaba de
        # coincidir con él y ganaba otra intención.
        match = match_intent(
            query_text, intents,
            embed_query=self._rag.embed_query, embed_texts=self._embed_reference_texts,
            text_transform=self._catalog_mention_masker(project_id),
        )

        intent_scores = [
            IntentScoreView(
                intent_name=score.intent.name, margin=score.margin, positive=score.positive,
                negative=score.negative, priority=score.intent.priority,
            )
            for score in (match.scores if match is not None else [])
        ]
        if match is None:
            decision = self._reranking_decision(project_id)
            return SimulationTrace(
                query_text=query_text, provided_variables=provided, action=RuleActionType.ABSTENERSE,
                abstention_reason="Ninguna intención activa coincide con esta consulta -- el documento "
                "maestro exige abstenerse (o canalizar) antes que responder con una intención adivinada.",
                reranking_setting=decision[0],
                reranking_available=self._rag.reranker_loaded,
                reranking_available_model=self._rag.reranker_model_name,
                reranking_model_status="cargado" if decision[1] else "no_requerido",
                runtime_effective_reranking="con_reranking" if decision[1] else "sin_reranking",
                retrieval_pipeline=procedure,
            )

        intent, confidence = match.intent, match.confidence
        # Ronda 89 (hallazgo real de usuario, AGENTE UDL): las variables
        # de la intención que no vinieron explícitamente se buscan en el
        # propio texto de la consulta, con los catálogos/valores de
        # metadatos del proyecto. Lo explícito siempre tiene prioridad.
        detected, ambiguous = self._detect_variables(project_id, query_text, intent, provided)
        effective = {**detected, **provided}
        missing = [
            code for code in intent.required_variables if not (effective.get(code) or "").strip()
        ]

        context = {
            "intencion": intent.name,
            "confianza": str(confidence),
            "nivel_riesgo": intent.risk_level.value,
            "variables_faltantes": "1" if missing else "0",
        }
        guardrails = [rule for rule in self._guardrails.list_for_project(project_id) if rule.active]
        rule_action, fired = select_firing_action(guardrails, context)

        # Datos mínimos faltantes: siempre exige aclarar antes de
        # responder, sin importar lo que hayan decidido las reglas de
        # guardrail -- es la "regla de oro" de B2 (RAG STUDIO.odt): no
        # se genera una respuesta definitiva con datos mínimos
        # incompletos. Se combina por severidad (nunca se "relaja" a
        # RESPONDER si una regla ya pidió algo más severo, como
        # canalizar).
        baseline_action = RuleActionType.ACLARAR if missing else RuleActionType.RESPONDER
        final_action = max((rule_action, baseline_action), key=lambda a: ACTION_SEVERITY[a])

        clarifying_question: Optional[str] = None
        if final_action == RuleActionType.ACLARAR:
            if missing:
                clarifying_question = intent.clarifying_questions.get(
                    missing[0], f"¿Podrías indicar el dato '{missing[0]}'?"
                )
            else:
                clarifying_question = "Se requiere aclaración adicional antes de responder (regla activada)."

        channeling: Optional[ChannelingScheme] = None
        channeling_note: Optional[str] = None
        if final_action == RuleActionType.CANALIZAR and not intent.fallback_channeling_code:
            channeling_note = (
                f"La intención {intent.name!r} no tiene canalización alternativa: se decidió canalizar, "
                "pero no hay esquema que usar. Edite la intención y escriba el código del esquema en "
                "\"Canalización alternativa\"."
            )
        if final_action == RuleActionType.CANALIZAR and intent.fallback_channeling_code:
            channeling = self._channeling.get_by_code(project_id, intent.fallback_channeling_code)
            if channeling is None:
                channeling_note = (
                    f"La canalización alternativa de la intención {intent.name!r} es "
                    f"{intent.fallback_channeling_code!r}, pero no existe ningún esquema con ese código. "
                    "Revise que el código coincida exactamente con el de la pestaña Canalización."
                )
            elif not channeling.active:
                channeling_note = (
                    f"El esquema {channeling.code!r} está inactivo: se decidió canalizar, pero un esquema "
                    "inactivo no genera paquete. Actívelo en la pestaña Canalización."
                )
            # Auditoria profunda (ronda posterior a la 76, ver bitacora):
            # a diferencia de las Intent (filtradas por `active` dentro de
            # match_intent, domain.conversational.intent_matching) y las
            # GuardrailRule (filtradas por `active` un poco mas arriba en
            # este mismo metodo), get_by_code() nunca filtraba por
            # `active` -- un ChannelingScheme desactivado (p. ej. porque
            # el buzon/webhook de destino ya no existe) seguia
            # canalizandose de verdad. "Desactivar, nunca borrar, para
            # que deje de tener efecto" es el mismo criterio para los
            # tres mecanismos de este motor de decision.
            if channeling is not None and not channeling.active:
                channeling = None

        search_results: list[SemanticSearchResult] = []
        result_ordering: list[ResultOrderingView] = []
        reranking_setting, use_rerank, reranking_note = self._reranking_decision(project_id)
        reranking_applied = False
        search_text: Optional[str] = None
        retrieval_query: Optional[str] = None
        section_ordering = False
        applied_filters: dict[str, str] = {}
        excluded_count = 0
        abstention_reason: Optional[str] = None
        structured_result: Optional[StructuredQueryResult] = None
        image_results: list[ImageSearchResult] = []
        ambiguous_references: list[str] = []
        tried_structured = False

        if final_action == RuleActionType.RESPONDER:
            if intent.resolution_mode == IntentResolutionMode.ESTRUCTURADO:
                tried_structured = True
                candidate = self._query_structured(
                    project_id, effective, source_id=source_id, max_access_level=max_access_level,
                )
                if candidate.rows:
                    # Resuelto por la vía estructurada -- no se hace
                    # también búsqueda semántica (Pista B.4, Opción B
                    # del documento de diseño: un único camino ganador
                    # por respuesta, nunca ambos mezclados).
                    structured_result = candidate

            if structured_result is None:
                # SEMANTICO de entrada, o ESTRUCTURADO sin ninguna fila
                # -- degradación automática a vector+BM25 (sección 4.3
                # del documento de diseño de B.4): marcar una intención
                # como ESTRUCTURADO nunca debe dejarla peor que si
                # hubiera quedado en SEMANTICO.
                ambiguous_sink: list[str] = []
                (
                    search_results, applied_filters, excluded_count, retrieval_query, result_ordering,
                ) = self._search_and_filter(
                    project_id, query_text, effective, source_id=source_id, limit=limit,
                    max_access_level=max_access_level, intent=intent, intents=intents, rerank=use_rerank,
                    procedure=procedure, ambiguous_sink=ambiguous_sink,
                )
                ambiguous_references = ambiguous_sink
                reranking_applied = use_rerank
                search_text = retrieval_query or query_text
                section_ordering = bool(applied_filters) and self._sources is not None
                if not search_results:
                    final_action = RuleActionType.ABSTENERSE
                    abstention_reason = (
                        "La búsqueda no devolvió resultados utilizables (vigentes y validados) "
                        "para esta consulta -- el motor conversacional nunca responde con contenido "
                        "de otro contexto ni con fuentes no autorizadas."
                        + (
                            " Tampoco la vía estructurada (Pista B.4) encontró ninguna fila."
                            if tried_structured else ""
                        )
                        + self._empty_filter_hint(project_id, applied_filters)
                    )

            # Fase 3/4 de multimodalidad nativa (RAG 3): tercer canal de
            # evidencia (imágenes), independiente de si la respuesta se
            # resolvió por texto o por datos estructurados -- nunca se
            # fusiona con search_results (ver docstring de
            # SimulationTrace.image_results). Se evalúa DESPUÉS de la
            # posible degradación a ABSTENERSE de arriba: si el texto no
            # encontró nada utilizable, no tiene sentido buscar además
            # imágenes para una respuesta que ya no se va a dar.
            # has_image_search (capacidad opcional, mismo criterio que
            # has_reranker en _search_and_filter): un proyecto sin
            # image_embedding_provider configurado simplemente no
            # intenta esta búsqueda, sin ningún error.
            if final_action == RuleActionType.RESPONDER and self._rag.has_image_search:
                image_results = self._rag.search_images(
                    project_id, query_text, limit=limit, source_id=source_id,
                    only_usable_sources=True, max_access_level=max_access_level,
                )

        return SimulationTrace(
            query_text=query_text, provided_variables=provided,
            matched_intent_name=intent.name, confidence=confidence,
            required_variables=intent.required_variables, missing_variables=missing,
            clarifying_question=clarifying_question,
            fired_rules=[rule.name for rule in fired], action=final_action, channeling=channeling,
            channeling_note=channeling_note,
            detected_variables=detected, ambiguous_variables=ambiguous, retrieval_query=retrieval_query,
            intent_scores=intent_scores, section_ordering=section_ordering,
            applied_metadata_filters=applied_filters, excluded_by_metadata_filter=excluded_count,
            search_results=search_results, abstention_reason=abstention_reason,
            structured_result=structured_result, image_results=image_results,
            result_ordering=result_ordering, reranking_setting=reranking_setting,
            reranking_applied=reranking_applied,
            reranking_model=self._rag.reranker_model_name if reranking_applied else None,
            reranking_note=reranking_note, reranking_available=self._rag.reranker_loaded,
            reranking_available_model=self._rag.reranker_model_name, search_text=search_text,
            reranking_model_status="cargado" if use_rerank else "no_requerido",
            runtime_effective_reranking="con_reranking" if use_rerank else "sin_reranking",
            retrieval_pipeline=procedure, ambiguous_references=ambiguous_references,
        )

    def _procedure_decision(self, project_id: str) -> str:
        """Ronda 106: procedimiento de recuperación efectivo del proyecto
        ("r105b" o "r106"). Sin ajuste guardado, "r105b". Un valor que este
        código no conoce produce UnknownRetrievalProcedureError (nunca se
        sustituye en silencio por otro procedimiento)."""
        guardado = self._retrieval_procedure(project_id) if self._retrieval_procedure is not None else None
        return validate_procedure(guardado)

    def _reranking_decision(self, project_id: str) -> tuple[str, bool, Optional[str]]:
        """(ajuste, si se aplica reranking, aviso).

        Ronda 105b (P1, alternativa B estricta, decisión de NEXOM): la
        configuración efectiva es la misma en el Simulador y en el Runtime.
        - Automático (predeterminado) y Desactivado: SIN reranking, haya o no
          modelo. (Hasta la Ronda 105, Automático aplicaba el reranking si
          había modelo: el Simulador sí lo hacía y el Runtime nunca.)
        - Activado: CON reranking; antes de buscar se verifica que el modelo
          esté disponible y cargado. Si no, RerankingRequiredUnavailableError:
          error explícito, nunca una respuesta sin reranking."""
        ajuste = self._agent_reranking(project_id) if self._agent_reranking is not None else None
        if ajuste is True:
            self._rag.ensure_reranker_ready()
            return RERANKING_ACTIVADO, True, None
        if ajuste is False:
            return RERANKING_DESACTIVADO, False, None
        return RERANKING_AUTOMATICO, False, None

    def _query_structured(
        self, project_id: str, provided: dict[str, str], source_id: Optional[str],
        max_access_level: Optional[AccessLevel] = None,
    ) -> StructuredQueryResult:
        """Pista B.4 del ADR-003: deriva filtros de igualdad de las
        variables ya proporcionadas en la conversación, mismo puente
        "Dato conversacional -> Campo -> Filtro" que _search_and_filter
        ya usa para metadatos (arriba), aplicado aquí a
        ConversationalVariable.structured_column en vez de a
        metadata_field_id. Solo filtros (sin agregación) en esta
        primera fase -- derivar una agregación con group_by/función a
        partir de la conversación queda fuera de este alcance, ver
        documento de diseño de B.4, sección 4.2.

        only_usable_sources=True siempre (auditoría posterior a la
        Ronda 76): un motor conversacional real debe forzarlo, mismo
        criterio exacto que _search_and_filter aplica a la vía
        semántica -- antes de esta corrección, la vía ESTRUCTURADA era
        la única de las dos que no lo hacía. max_access_level se
        reenvía tal cual, igual que en _search_and_filter."""
        variables = self._variables.list_for_project(project_id)
        filters = [
            StructuredFilter(
                column=variable.structured_column, operator=StructuredFilterOperator.IGUAL,
                value=provided[variable.code].strip(),
            )
            for variable in variables
            if variable.structured_column and (provided.get(variable.code) or "").strip()
        ]
        return self._rag.query_structured(
            project_id, filters=filters or None, source_id=source_id,
            only_usable_sources=True, max_access_level=max_access_level,
        )

    def _search_and_filter(
        self, project_id: str, query_text: str, provided: dict[str, str],
        source_id: Optional[str], limit: int,
        max_access_level: Optional[AccessLevel] = None,
        intent: Optional[Intent] = None, intents: Optional[list[Intent]] = None,
        rerank: Optional[bool] = None,
        procedure: str = "r105b",
        ambiguous_sink: Optional[list[str]] = None,
    ) -> tuple[list[SemanticSearchResult], dict[str, str], int, Optional[str], list[ResultOrderingView]]:
        # Un motor conversacional real siempre debe forzar
        # only_usable_sources=True (a diferencia del Laboratorio RAG de
        # Etapa 4, donde es opt-in para poder probar con borradores) --
        # ver README, "Limitaciones conocidas" de Etapa 4 sobre esta
        # misma decisión ya anotada de antemano. max_access_level
        # (Pista B.3) se reenvía tal cual -- None no agrega ningún
        # filtro nuevo.
        #
        # rerank=self._rag.has_reranker (Ronda 40, cierre de la Opción 1
        # de C.4 del ADR-003, docs proyecto/
        # RAG_STUDIO_Propuesta_C4_Aprendizaje_Retrieval.docx): el
        # consultor condicionó activar el reranker por defecto en esta
        # vía de producción a que se midiera antes su costo real de
        # latencia. scripts/benchmark_reranker_latency.py, corrido por
        # el propio consultor contra su proyecto real, midió un costo
        # adicional de +90.6 ms por consulta (delta de p50) -- se
        # decidió que ese costo es aceptable frente al valor esperado
        # de reordenar con un cross-encoder real en vez de solo RRF. No
        # se usa un booleano fijo (True) para no romper quien construya
        # RagService sin ningún Reranker configurado (p. ej. varias
        # pruebas de esta misma suite): en ese caso has_reranker es
        # False y el comportamiento no cambia respecto a antes de esta
        # ronda.
        # Ronda 102 (C4): el ajuste del proyecto decide (ver
        # _reranking_decision). Ronda 105b (P1): sin decisión explícita, sin
        # reranking (el texto de arriba describe el criterio anterior).
        if rerank is None:
            rerank = False
        variables = self._variables.list_for_project(project_id)
        active_filters = {
            variable.code: provided[variable.code].strip()
            for variable in variables
            if variable.metadata_field_id and (provided.get(variable.code) or "").strip()
        }
        if not active_filters:
            raw_results = self._rag.search_hybrid(
                project_id, query_text, limit=limit, source_id=source_id, only_usable_sources=True,
                rerank=rerank, max_access_level=max_access_level,
            )
            return raw_results, {}, 0, None, []

        # Ronda 89 (hallazgo real de usuario, AGENTE UDL: "revisar si el
        # filtro se aplica antes o después de seleccionar los primeros
        # resultados"): antes se buscaba el top-k de TODO el proyecto y
        # luego se descartaban los resultados de otras fuentes -- con la
        # pregunta completa quedaban 2 fragmentos (identificación y
        # título) y el fragmento "Objetivo" nunca llegaba. Ahora se
        # calcula primero qué fuentes cumplen los filtros y se busca solo
        # dentro de ellas. Sin repositorio de fuentes (construcción
        # antigua) se conserva el filtrado posterior de siempre.
        if self._sources is not None:
            all_sources = self._sources.list_for_project(project_id)
            allowed = {
                source.id for source in all_sources
                if self._source_matches_filters(project_id, source.id, variables, active_filters)
            }
            retrieval_query = self._retrieval_query(project_id, query_text, variables, active_filters, allowed)
            text_for_search = retrieval_query or query_text
            # Ronda 91 (hallazgo real de usuario): con el filtro aplicado,
            # todos los candidatos son del programa correcto y lo que falta
            # es elegir el APARTADO. Se pide un conjunto más amplio, se
            # ponen primero las secciones afines a la intención (ver
            # domain.conversational.section_affinity) y se conserva el
            # orden de la búsqueda entre secciones igual de afines.
            pool = max(limit * 4, 20) if intent is not None else limit
            results = self._rag.search_hybrid(
                project_id, text_for_search, limit=pool, source_id=source_id, only_usable_sources=True,
                rerank=rerank, max_access_level=max_access_level, source_ids=allowed,
            )
            ordering: list[ResultOrderingView] = []
            if intent is not None:
                afinidad = SectionAffinity(
                    intent, intents or [intent], query_text, self._catalog_mention_masker(project_id),
                )
                titulos_fuente = {source.id: source.title for source in all_sources}
                puesto_busqueda = {r.chunk.id: n for n, r in enumerate(results, start=1)}
                r106 = procedure == PROCEDURE_R106
                enlaces: dict[str, list[str]] = {}
                if r106:
                    # Ronda 106, componente R: el contenido de la fuente a la
                    # que remite un fragmento puente se inserta antes del
                    # puente. Destinos solo de este mismo conjunto (mismos
                    # filtros, vigencia y nivel de acceso).
                    resolucion = resolve_references(
                        results, {sid: titulos_fuente.get(sid, "") for sid in allowed},
                    )
                    results, enlaces = resolucion.candidates, resolucion.links
                    if ambiguous_sink is not None:
                        ambiguous_sink.extend(resolucion.ambiguous)
                titulos = [
                    _section_title(r.chunk, titulos_fuente.get(r.chunk.source_id), exclude_yaml_only=r106)
                    for r in results
                ]
                puntajes = [afinidad.score(titulo) for titulo in titulos]
                if r106:
                    # Componente V: la afinidad suma según su valor; después,
                    # la restricción de R (cada destino delante de su puente).
                    orden_completo = combine_by_value(puntajes)
                    indice = {r.chunk.id: i for i, r in enumerate(results)}
                    orden_ids = enforce_destinations_first([results[i].chunk.id for i in orden_completo], enlaces)
                    orden = [indice[cid] for cid in orden_ids][:limit]
                else:
                    # Ronda 102 (C1, hallazgo real de NEXOM): la afinidad ya no
                    # es la clave principal; se combina por RRF con el orden de
                    # la búsqueda (ver combine_with_retrieval).
                    orden = combine_with_retrieval(puntajes)[:limit]
                puentes_de: dict[str, list[str]] = {}
                for destino, puentes in enlaces.items():
                    puentes_de[destino] = list(puentes)
                fuente_de = {r.chunk.id: r.chunk.source_id for r in results}
                ordering = [
                    ResultOrderingView(
                        retrieval_rank=puesto_busqueda[results[i].chunk.id], affinity=round(puntajes[i], 3),
                        affinity_title=titulos[i],
                        referenced_from=puentes_de.get(results[i].chunk.id, []),
                        referenced_from_sources=list(dict.fromkeys(
                            titulos_fuente.get(fuente_de.get(p, ""), "") for p in puentes_de.get(results[i].chunk.id, [])
                        )),
                    )
                    for i in orden
                ]
                results = [results[i] for i in orden]
            return results, active_filters, len(all_sources) - len(allowed), retrieval_query, ordering

        retrieval_query = self._retrieval_query(project_id, query_text, variables, active_filters, None)
        text_for_search = retrieval_query or query_text
        raw_results = self._rag.search_hybrid(
            project_id, text_for_search, limit=limit, source_id=source_id, only_usable_sources=True,
            rerank=rerank, max_access_level=max_access_level,
        )
        filtered: list[SemanticSearchResult] = []
        excluded = 0
        for result in raw_results:
            if self._matches_all_filters(project_id, result, variables, active_filters):
                filtered.append(result)
            else:
                excluded += 1
        return filtered, active_filters, excluded, retrieval_query, []

    def _matches_all_filters(
        self, project_id: str, result: SemanticSearchResult,
        variables: list, active_filters: dict[str, str],
    ) -> bool:
        for variable in variables:
            if variable.code not in active_filters:
                continue
            if not self._source_value_matches(
                project_id, result.chunk.source_id, variable.metadata_field_id, active_filters[variable.code],
            ):
                return False
        return True

    def _source_matches_filters(
        self, project_id: str, source_id: str, variables: list, active_filters: dict[str, str],
    ) -> bool:
        return all(
            self._source_value_matches(project_id, source_id, variable.metadata_field_id, active_filters[variable.code])
            for variable in variables if variable.code in active_filters
        )

    def _source_value_matches(self, project_id: str, source_id: str, field_id: str, expected: str) -> bool:
        """Ronda 89: un campo de valor múltiple se guarda como "a|b"; antes
        se comparaba el texto completo y una fuente con "a|b" nunca
        coincidía con el filtro "a"."""
        stored = self._source_metadata.get_value(project_id, source_id, field_id)
        if stored is None:
            return False
        valores = {v.strip().lower() for v in stored.value.split("|") if v.strip()}
        return expected.strip().lower() in valores

    # ---------- Ronda 89: variables en el texto de la consulta ----------

    def _empty_filter_hint(self, project_id: str, applied_filters: dict[str, str]) -> str:
        """Ronda 89 (auditoría con AGENTE UDL): si NINGUNA fuente tiene el
        valor filtrado, decirlo -- suele ser un valor sin capturar (o mal
        capturado) en Metadatos > Valores por fuente, no una pregunta sin
        respuesta."""
        if not applied_filters or self._sources is None:
            return ""
        variables = self._variables.list_for_project(project_id)
        if any(
            self._source_matches_filters(project_id, source.id, variables, applied_filters)
            for source in self._sources.list_for_project(project_id)
        ):
            return ""
        filtros = ", ".join(f"{k}={v}" for k, v in applied_filters.items())
        return (
            f" Ninguna fuente del proyecto tiene asignado {filtros}: revise Metadatos > Valores por "
            "fuente (puede faltar capturarlo o estar asignado a otro valor)."
        )

    _MAX_REFERENCE_VECTORS = 20000

    def _embed_reference_texts(self, texts: list[str]) -> list[list[float]]:
        # Si cambia el proveedor de embeddings (otro modelo), los vectores
        # guardados ya no son comparables: se descartan.
        proveedor = id(getattr(self._rag, "_embedding_provider", self._rag))
        if getattr(self, "_reference_vectors_provider", None) != proveedor:
            self._reference_vectors.clear()
            self._reference_vectors_provider = proveedor
        pendientes = [t for t in dict.fromkeys(texts) if t not in self._reference_vectors]
        if pendientes:
            if len(self._reference_vectors) + len(pendientes) > self._MAX_REFERENCE_VECTORS:
                self._reference_vectors.clear()
            for texto, vector in zip(pendientes, self._rag.embed_texts(pendientes), strict=True):
                self._reference_vectors[texto] = vector
        return [self._reference_vectors[t] for t in texts]

    def _catalog_mention_masker(self, project_id: str) -> Optional[Callable[[str], str]]:
        """Función que quita de un texto las menciones de valores de
        catálogo de las variables ligadas a metadatos (p. ej. nombres de
        programas). Esas palabras dicen DE QUÉ programa se pregunta, no QUÉ
        se pregunta. Se aplica igual a la consulta y a los ejemplos de las
        intenciones (Ronda 90). None si no hay nada que quitar."""
        if self._schemas is None and self._sources is None:
            return None
        # Ronda 91 (hallazgo real de usuario): además de los campos ligados
        # a variables, TODOS los campos del esquema que usan catálogo (p.
        # ej. nivel_academico = "Licenciatura"). Antes solo se quitaban los
        # primeros; la búsqueda de fragmentos sí quitaba los demás
        # (_retrieval_query), y esa diferencia hacía que "... termina la
        # licenciatura en Derecho" se pareciera a "Cuéntame sobre la
        # licenciatura en Psicología" (otra intención) por la palabra
        # "licenciatura", que no dice QUÉ se pregunta.
        field_ids: list[str] = []
        for variable in self._variables.list_for_project(project_id):
            if variable.metadata_field_id and variable.metadata_field_id not in field_ids:
                field_ids.append(variable.metadata_field_id)
        if self._schemas is not None:
            schema = self._schemas.get_active_schema(project_id)
            if schema is not None:
                for field in self._schemas.list_fields(project_id, schema.id):
                    if field.catalog_id and field.field_id not in field_ids:
                        field_ids.append(field.field_id)
        aliases: list[tuple[str, ...]] = []
        for field_id in field_ids:
            aliases.extend(c.aliases for c in self._candidates_for_field(project_id, field_id))
        if not aliases:
            return None

        def mask(text: str) -> str:
            spans = [(start, end) for group in aliases for _, start, end in find_mentions(text, group)]
            if not spans:
                return text
            masked = remove_spans(text, spans)
            return masked if any(len(word) >= 4 for word in masked.split()) else text

        return mask

    def _candidates_for_field(self, project_id: str, field_id: str) -> list[ValueCandidate]:
        """Valores posibles de un campo de metadatos: las entradas de su
        catálogo (código + etiqueta) o, si no usa catálogo, los valores ya
        capturados en las fuentes del proyecto. Nunca listas fijas."""
        if self._schemas is not None and self._catalogs is not None:
            schema = self._schemas.get_active_schema(project_id)
            field = self._schemas.get_field(project_id, schema.id, field_id) if schema else None
            if field is not None and field.catalog_id:
                return [
                    ValueCandidate(entry.value_code, alias_forms(entry.label, entry.value_code))
                    for entry in self._catalogs.list_entries(project_id, field.catalog_id)
                ]
        if self._sources is None:
            return []
        valores: set[str] = set()
        for source in self._sources.list_for_project(project_id):
            stored = self._source_metadata.get_value(project_id, source.id, field_id)
            if stored is not None:
                valores.update(v.strip() for v in stored.value.split("|") if v.strip())
        return [ValueCandidate(valor, alias_forms(valor)) for valor in sorted(valores)]

    def _detect_variables(
        self, project_id: str, query_text: str, intent, provided: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        if self._schemas is None and self._sources is None:
            return {}, {}
        wanted = [
            code for code in list(intent.required_variables) + list(intent.optional_variables)
            if not (provided.get(code) or "").strip()
        ]
        if not wanted:
            return {}, {}
        by_code = {v.code: v for v in self._variables.list_for_project(project_id)}
        candidates: dict[str, list[ValueCandidate]] = {}
        for code in wanted:
            field_id = by_code[code].metadata_field_id if code in by_code else None
            if field_id:
                candidates[code] = self._candidates_for_field(project_id, field_id)
        result = extract_variable_values(query_text, {k: v for k, v in candidates.items() if v})
        return result.detected, result.ambiguous

    def _retrieval_query(
        self, project_id: str, query_text: str, variables: list, active_filters: dict[str, str],
        allowed_source_ids: Optional[set[str]],
    ) -> Optional[str]:
        """Texto para buscar fragmentos una vez aplicados los filtros (Ronda
        89): sin las menciones de valores de metadatos que ya no
        distinguen nada entre los candidatos -- los valores filtrados y,
        además, cualquier valor de metadatos que TODAS las fuentes
        permitidas comparten (p. ej. su nivel académico). Esas palabras
        aparecen en el título y en la ficha de identificación de la
        fuente, y empujaban esos fragmentos por encima del que de verdad
        responde la pregunta ("Objetivo"). Si no queda ninguna palabra
        útil, se usa la consulta original."""
        valores_constantes: dict[str, set[str]] = {}
        by_code = {v.code: v for v in variables}
        for code, value in active_filters.items():
            variable = by_code.get(code)
            if variable is not None and variable.metadata_field_id:
                valores_constantes.setdefault(variable.metadata_field_id, set()).add(value.strip().lower())
        if allowed_source_ids:
            compartidos: Optional[dict[tuple[str, str], int]] = None
            for allowed_id in allowed_source_ids:
                pares = {
                    (stored.field_id, v.strip().lower())
                    for stored in self._source_metadata.list_values_for_source(project_id, allowed_id)
                    for v in stored.value.split("|") if v.strip()
                }
                compartidos = {p: 1 for p in pares} if compartidos is None else {
                    p: 1 for p in compartidos if p in pares
                }
            for field_id, value in (compartidos or {}):
                valores_constantes.setdefault(field_id, set()).add(value)

        spans: list[tuple[int, int]] = []
        for field_id, values in valores_constantes.items():
            for candidate in self._candidates_for_field(project_id, field_id):
                if candidate.value.strip().lower() in values:
                    spans.extend((start, end) for _, start, end in find_mentions(query_text, candidate.aliases))
        if not spans:
            return None
        stripped = remove_spans(query_text, spans)
        if not any(len(word) >= 4 for word in stripped.split()):
            return None
        return stripped if stripped != query_text else None

