"""Esquemas HTTP de interfaces/api/ (ADR-002, Fase 2). Deliberadamente
separados de los modelos de application/domain (SimulationTrace,
ConversationLogEntry, Chunk...) -- mismo criterio de capa que ui/
(nunca expone un objeto de dominio tal cual a través de una interfaz;
lo traduce), para no atar el contrato HTTP a la forma interna del
motor conversacional."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from application.runtime.commands.handle_incoming_message import HandledMessage
from domain.documents.entities import AccessLevel
from domain.quality.entities import EvaluationRun, relative_drop
from domain.runtime.entities import ConversationMetricsSummary, FeedbackSignal, WidgetToken


class MessageRequest(BaseModel):
    # max_length (auditoría Ronda 10, hallazgo B11): el token de widget
    # viaja, por diseño, en el HTML público del sitio del cliente --
    # cualquiera puede extraerlo y enviar mensajes arbitrariamente
    # grandes en bucle. Cada uno se persiste completo en
    # conversation_log.message (sin límite propio, ver
    # infrastructure/database/runtime_repositories.py) y dispara una
    # búsqueda vectorial real. Un límite razonable (mucho más que
    # cualquier pregunta real) acota el costo por solicitud sin exigir
    # todavía un limitador de tasa (eso queda mejor resuelto en el
    # proxy inverso del despliegue, ver GUIA_DESPLIEGUE.md).
    message: str = Field(min_length=1, max_length=2000, description="El mensaje real del usuario del canal.")
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Datos ya conocidos de la conversación (mismo concepto que 'variables proporcionadas' "
        "en el Simulador) -- p. ej. {'plantel': 'Campus Norte'} si el canal ya los capturó antes.",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Ronda 19: id de la conversación en curso, tal cual llegó en el 'conversation_id' de "
        "una respuesta anterior de esta misma conversación. Omitirlo (o mandar None) en el primer "
        "mensaje -- el servidor genera uno nuevo y lo devuelve; reenviarlo en los turnos siguientes "
        "agrupa los mensajes del lado del servidor (bitácora de Monitoreo, banco de pruebas), sin "
        "que el canal (widget u otro) tenga que mantener ningún estado de sesión propio.",
    )


class SourceSnippet(BaseModel):
    source_id: str
    chunk_id: str
    text: str
    score: float
    page_start: Optional[int] = Field(
        default=None,
        description="Pista C.5 del ADR-003 (roadmap de pendientes de RAG 5, Ronda 43/44): número de "
        "página (1-indexado) donde empieza este fragmento, solo para fuentes PDF -- mismo dato que "
        "domain.ingestion.entities.Chunk.page_start, ya calculado desde antes de la Pista C "
        "(ExtractionRecord.page_breaks -> resolve_page()) y ya visible en el Laboratorio RAG, pero "
        "nunca expuesto por HTTP hasta ahora. None para fuentes sin páginas (TXT/DOCX/Markdown) o "
        "cuando no se pudo resolver. Campo aditivo: un agente que hoy solo lee 'text'/'score' sigue "
        "funcionando exactamente igual si lo ignora.",
    )
    page_end: Optional[int] = Field(
        default=None,
        description="Mismo origen y mismas condiciones que page_start -- página donde termina el "
        "fragmento. Puede ser igual a page_start (fragmento contenido en una sola página) o mayor "
        "(fragmento que cruza un salto de página).",
    )
    section_title: Optional[str] = Field(
        default=None,
        description="Ronda 58: título de la sección o encabezado de origen del fragmento (p. ej. "
        "'3.2 Requisitos de inscripción'), mismo dato que domain.ingestion.entities.Chunk."
        "section_title -- ya poblado desde la Pista B.1 del ADR-003 y ya expuesto en "
        "StructuredResultRow.section_title, pero nunca antes en 'sources'. None cuando la "
        "estrategia de fragmentación de la fuente no produce encabezados (solo "
        "POR_ENCABEZADO lo puebla por ahora, ver application/ingestion/commands/"
        "fragment_source.py) o cuando el fragmento no cayó bajo ningún encabezado. Campo "
        "aditivo: un agente que hoy solo lee 'text'/'score' sigue funcionando exactamente "
        "igual si lo ignora.",
    )
    retrieval_rank: Optional[int] = Field(
        default=None,
        description="Ronda 104b (Etapa 0, diagnóstico): puesto del fragmento en la recuperación inicial, "
        "antes del reordenamiento conversacional. Solo con la credencial operativa (X-API-Key); null "
        "con token de widget. Campo aditivo.",
    )
    affinity: Optional[float] = Field(
        default=None,
        description="Ronda 104b (Etapa 0, diagnóstico): afinidad título-intención usada al ordenar "
        "(null si no hubo reordenamiento por afinidad). Solo con la credencial operativa. Campo aditivo.",
    )


class ImageResultSnippet(BaseModel):
    """Fase 3/4 de multimodalidad nativa (RAG 3): traducción de
    application.rag.queries.semantic_search_images.ImageSearchResult
    -- nunca se expone el Chunk de dominio tal cual, mismo criterio de
    capa que SourceSnippet. Deliberadamente sin 'text' (un chunk tipo
    IMAGEN no tiene texto narrativo, ver domain.ingestion.entities.
    ChunkType.IMAGEN) -- image_relative_path es la referencia real al
    contenido."""

    source_id: str
    chunk_id: str
    image_relative_path: Optional[str] = Field(
        default=None,
        description="Ruta relativa dentro de sources/original/ del proyecto (ver "
        "domain.ingestion.entities.Chunk.image_relative_path) -- el agente externo necesita "
        "resolverla contra su propia copia del proyecto/instantánea para poder mostrar la imagen; "
        "este endpoint no sirve el archivo en sí.",
    )
    score: float


class StructuredResultRow(BaseModel):
    """Pista B.4 del ADR-003 -- traducción de
    domain.rag.structured_query.StructuredQueryRow (nunca se expone el
    tipo de dominio tal cual por HTTP, ver docstring del módulo)."""

    chunk_id: str
    source_id: str
    section_title: Optional[str] = None
    row_index: int = Field(
        description="Pista C.2a del ADR-003: posición (0-based) de esta fila dentro del bloque "
        "estructurado de origen -- permite al agente citar la fila exacta (p. ej. \"según la fila "
        "4 de la hoja Costos\") en vez de solo los valores, que por sí solos no distinguen dos "
        "filas idénticas. Campo aditivo, agregado después de que este esquema ya existía.",
    )
    values: dict[str, Any]


class StructuredResultBucket(BaseModel):
    """Traducción de domain.rag.structured_query.StructuredAggregationBucket.
    Reservado -- ver StructuredResult.aggregation."""

    group_value: Optional[str] = None
    value: Optional[float] = None


class StructuredResult(BaseModel):
    rows: list[StructuredResultRow] = Field(default_factory=list)
    aggregation: Optional[list[StructuredResultBucket]] = Field(
        default=None,
        description="Reservado para una fase futura de la Pista B.4 -- hoy SimulateConversation "
        "solo deriva filtros de las variables de la conversación, nunca una agregación; este "
        "campo siempre llega None en esta versión.",
    )


class ErrorInfo(BaseModel):
    """Ronda 93: diagnóstico de una solicitud que no pudo atenderse --
    antes, un fallo del motor respondía 500 "Internal Server Error" en texto
    plano y el consumidor no podía saber la causa."""

    category: str = Field(description="Ver domain.runtime.failures.FailureCategory; nunca vacío.")
    stage: str = Field(description="Etapa donde ocurrió (FailureStage).")
    code: str = Field(description="Código estable y corto, p. ej. 'embedding.model_unavailable'.")
    message: str = Field(description="Mensaje resumido para operación.")
    trace_id: str
    log_id: Optional[str] = Field(
        default=None,
        description="Id del turno fallido guardado en runtime.db (pestaña Monitoreo); null si no "
        "pudo guardarse o si el error ocurrió antes de identificar el proyecto.",
    )
    snapshot_version: Optional[int] = None
    exception_type: Optional[str] = None
    timestamp: str
    retryable: bool = Field(description="True si reintentar más tarde puede funcionar (bloqueos, tiempo de espera).")


class ErrorResponse(BaseModel):
    detail: str
    error: ErrorInfo


class ExecutionCode(BaseModel):
    version: Optional[str] = None
    commit: Optional[str] = None
    commit_source: Optional[str] = Field(default=None, description='"build_info", "git" o null (desconocido).')
    dirty: Optional[bool] = None
    fingerprint: Optional[str] = Field(
        default=None, description="Huella SHA-256 del código (ver infrastructure/build_info.py).",
    )
    fingerprint_source: Optional[str] = None
    packages: list[str] = Field(default_factory=list)
    build_generated_at: Optional[str] = None
    unknown: list[str] = Field(default_factory=list)


class ExecutionSnapshot(BaseModel):
    project_id: Optional[str] = None
    version: Optional[int] = None
    identity_file: bool = False
    identity_error: Optional[str] = None
    declared_fingerprint: Optional[str] = Field(
        default=None, description="content_fingerprint de snapshot_identity.json (al publicar).",
    )
    published_at: Optional[str] = None
    fingerprint_at_load: Optional[str] = Field(
        default=None, description="Huella calculada al cargar la instantánea en este proceso.",
    )
    fingerprint_matches: Optional[bool] = None


class ExecutionIndex(BaseModel):
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    dimensions: Optional[int] = None
    points_count: Optional[int] = None
    updated_at: Optional[str] = None
    query_embedding_profile: Optional[str] = None
    query_embedding_model: Optional[str] = None


class ExecutionReranking(BaseModel):
    setting: str = Field(description='Ajuste del proyecto: "automatico", "activado" o "desactivado".')
    model_available: bool = Field(description="Ronda 105b: True solo si el modelo está cargado y verificado.")
    available_model: Optional[str] = None
    applied: bool
    model: Optional[str] = None
    note: Optional[str] = None
    model_status: Optional[str] = Field(
        default=None, description='Ronda 105b: "no_requerido" (Automático/Desactivado) o "cargado" (Activado).',
    )
    effective_in_runtime: Optional[str] = Field(
        default=None, description='Ronda 105b: "sin_reranking" o "con_reranking" (igual en Simulador y Runtime).',
    )


class ExecutionResult(BaseModel):
    position: int
    chunk_id: str
    source_id: str
    score: float
    retrieval_rank: Optional[int] = None
    affinity: Optional[float] = None


class ExecutionInfo(BaseModel):
    """Ronda 104b (Etapa 0, autorizada por NEXOM): con qué código,
    instantánea, índice, procedimiento y configuración efectiva de reranking
    se produjo esta respuesta. Mismo contenido que runtime.db
    (conversation_log.execution). Sin credenciales, rutas ni secretos."""

    format_version: int = 1
    code: Optional[ExecutionCode] = None
    snapshot: Optional[ExecutionSnapshot] = None
    index: Optional[ExecutionIndex] = None
    retrieval_pipeline: Optional[str] = None
    reranking: Optional[ExecutionReranking] = None
    search_text: Optional[str] = None
    applied_filters: dict[str, str] = Field(default_factory=dict)
    excluded_sources: int = 0
    affinity_ordering: bool = False
    results: list[ExecutionResult] = Field(default_factory=list)
    unknown: list[str] = Field(
        default_factory=list, description="Datos que no se pudieron determinar (nunca se inventan).",
    )


class MessageResponse(BaseModel):
    action: str
    response_text: Optional[str]
    matched_intent: Optional[str]
    confidence: Optional[float]
    sources: list[SourceSnippet]
    snapshot_version: int
    log_id: str
    conversation_id: str = Field(
        description="Ronda 19: id de esta conversación -- siempre presente, generado por el servidor "
        "en el primer turno si el llamador no mandó ninguno en la solicitud. Reenviarlo tal cual en "
        "'conversation_id' de la siguiente solicitud (ver MessageRequest).",
    )
    latency_ms: float
    trace_id: Optional[str] = Field(
        default=None,
        description="Ronda 93: identificador de correlación de esta solicitud -- el enviado en el "
        "encabezado X-Trace-Id o uno generado por el servicio. También viaja en el encabezado de "
        "respuesta X-Trace-Id y en ragstudio-api.log.",
    )
    missing_variables: list[str] = Field(
        default_factory=list,
        description="Ronda 12: variables que el motor todavía necesita para resolver la intención "
        "reconocida (mismo dato que ya usa el Simulador de escritorio, trace.missing_variables) -- "
        "cuando action es 'aclarar', el primer elemento es la variable a la que corresponde "
        "response_text. Permite que un canal (p. ej. el widget) sepa a qué variable asociar la "
        "siguiente respuesta del visitante, sin que el motor conversacional necesite saberlo.",
    )
    structured_result: Optional[StructuredResult] = Field(
        default=None,
        description="Pista B.4 del ADR-003 (enrutamiento multi-índice determinista): presente "
        "solo cuando la intención resuelta usa la vía estructurada de la Pista B.2 y encontró "
        "datos -- filas ya filtradas de un bloque estructurado (XLSX/CSV), en vez de (nunca "
        "además de) fragmentos de texto en 'sources' para ese mismo turno. Campo aditivo: un "
        "agente que hoy solo lee 'sources' sigue funcionando exactamente igual si lo ignora.",
    )
    image_results: list[ImageResultSnippet] = Field(
        default_factory=list,
        description="Fase 3/4 de multimodalidad nativa (RAG 3): resultados de búsqueda por "
        "similitud visual sobre imágenes nativas indexadas -- espacio vectorial separado de "
        "'sources' (texto), nunca fusionado con ese ni con 'structured_result' para este mismo "
        "turno (Ronda 36: fusionar espacios vectoriales no comparables produce resultados sin "
        "sentido). Lista vacía cuando el proyecto no tiene soporte de imágenes configurado, "
        "cuando la acción de este turno no fue 'responder', o cuando de verdad no hubo ninguna "
        "imagen relevante -- estos tres casos no se distinguen aquí. Campo aditivo: un agente "
        "que hoy solo lee 'sources' sigue funcionando exactamente igual si lo ignora.",
    )
    execution: Optional[ExecutionInfo] = Field(
        default=None,
        description="Ronda 104b (Etapa 0): datos de ejecución para diagnóstico y reproducción -- código "
        "(versión, commit, huella), instantánea (versión y huellas), índice, procedimiento de "
        "recuperación, reranking efectivo (ajuste, disponibilidad, aplicación, modelo), texto de "
        "búsqueda, filtros y fragmentos en orden. Solo con la credencial operativa (X-API-Key); null "
        "con token de widget. Campo aditivo.",
    )

    @classmethod
    def from_handled_message(cls, handled: HandledMessage, include_execution: bool = False) -> "MessageResponse":
        """include_execution (Ronda 104b): agrega `execution` y los campos de
        diagnóstico de `sources` -- solo para la credencial operativa."""
        trace = handled.trace
        execution = handled.log_entry.execution if include_execution else None
        detalle = {r["chunk_id"]: r for r in (execution or {}).get("results", [])}
        return cls(
            action=trace.action.value,
            response_text=handled.log_entry.response_text,
            matched_intent=trace.matched_intent_name,
            # Ronda 10, hallazgo menor C11: `trace.confidence or None`
            # convertía una confianza legítima de 0.0 en None ("no hubo
            # confianza") -- se asigna tal cual, ya es Optional[float].
            confidence=trace.confidence,
            sources=[
                SourceSnippet(
                    source_id=result.chunk.source_id, chunk_id=result.chunk.id,
                    text=result.chunk.text, score=result.score,
                    page_start=result.chunk.page_start, page_end=result.chunk.page_end,
                    section_title=result.chunk.section_title,
                    retrieval_rank=detalle.get(result.chunk.id, {}).get("retrieval_rank"),
                    affinity=detalle.get(result.chunk.id, {}).get("affinity"),
                )
                for result in trace.search_results
            ],
            execution=ExecutionInfo(**execution) if execution else None,
            snapshot_version=handled.log_entry.snapshot_version,
            log_id=handled.log_entry.id,
            conversation_id=handled.log_entry.conversation_id,
            latency_ms=handled.log_entry.latency_ms or 0.0,
            trace_id=handled.log_entry.trace_id,
            missing_variables=trace.missing_variables,
            structured_result=(
                StructuredResult(
                    rows=[
                        StructuredResultRow(
                            chunk_id=row.chunk_id, source_id=row.source_id,
                            section_title=row.section_title, row_index=row.row_index, values=row.values,
                        )
                        for row in trace.structured_result.rows
                    ],
                ) if trace.structured_result is not None else None
            ),
            image_results=[
                ImageResultSnippet(
                    source_id=result.chunk.source_id, chunk_id=result.chunk.id,
                    image_relative_path=result.chunk.image_relative_path, score=result.score,
                )
                for result in trace.image_results
            ],
        )


class HealthResponse(BaseModel):
    status: str
    loaded_projects: list[str]
    snapshot_mode: str = "registro"
    """Ronda 92 (aditivo): "fija" si se sirve RAGSTUDIO_SNAPSHOT_DIR,
    "registro" si se resuelve la última publicada de RAGSTUDIO_HOME."""
    snapshot_project_id: Optional[str] = None
    snapshot_version: Optional[int] = None
    """Identidad de la instantánea fija -- la que verá cualquier consumidor
    posterior. Permite comprobar tras el arranque que la versión servida es
    la esperada. Nunca incluye rutas del servidor."""
    embedding_profile: Optional[str] = None
    code_version: Optional[str] = None
    """Ronda 104b (Etapa 0, aditivo): versión de RAG Studio. El commit y la
    huella del código están en GET /health/details (protegido)."""
    retrieval_pipeline: Optional[str] = None
    """Ronda 104b (Etapa 0, aditivo): procedimiento de recuperación del
    motor (ver RETRIEVAL_PIPELINE en simulate_conversation.py)."""


class HealthDetailsResponse(BaseModel):
    """Ronda 104b (Etapa 0): GET /health/details, protegido con la clave
    operativa. Detalles internos del despliegue para reproducir trazas: no
    se exponen en /health (público). Sin rutas ni secretos."""

    code: ExecutionCode
    retrieval_pipeline: str
    snapshot_mode: str
    embedding_profile: Optional[str] = None
    reranking_model_available: Optional[bool] = Field(
        default=None, description="null si todavía no se cargó ninguna instantánea en este proceso.",
    )
    reranking_available_model: Optional[str] = None
    pinned_snapshot: Optional[dict] = None
    loaded_snapshots: list[dict] = Field(default_factory=list)
    package_fingerprints: dict[str, str] = Field(default_factory=dict)


class MetricsResponse(BaseModel):
    """GET /projects/{project_id}/metrics (Pista C.1 del ADR-003, docs
    proyecto/RAG_STUDIO_Propuesta_C1_Observabilidad.docx) --
    observabilidad básica: capacidad administrativa opcional, de solo
    lectura, protegida por API key (nunca por un token de widget --
    mismo criterio que /projects/{id}/widget-tokens, ver
    _require_api_key en interfaces/api/app.py). Aditiva: no cambia
    nada de POST /messages ni de MessageResponse."""

    project_id: str
    since: Optional[datetime] = Field(
        default=None,
        description="Inicio de la ventana agregada (parámetro `since` de la solicitud, "
        "eco tal cual). `null` significa todo el histórico del proyecto.",
    )
    total_turns: int
    turns_by_action: dict[str, int]
    avg_latency_ms: Optional[float] = Field(
        default=None,
        description="`null` cuando no hay ningún turno con latencia capturada en la ventana "
        "(nunca 0.0, que sería un dato falso).",
    )
    p95_latency_ms: Optional[float] = Field(
        default=None,
        description="Pista C.5 del ADR-003 (roadmap de pendientes de RAG 5, Ronda 44): percentil "
        "95 de la latencia sobre los turnos con latencia capturada en la ventana. Mismas "
        "condiciones de `null` que avg_latency_ms.",
    )
    p99_latency_ms: Optional[float] = Field(
        default=None,
        description="Percentil 99 de la latencia -- mismo criterio que p95_latency_ms.",
    )
    abstention_rate: Optional[float] = Field(
        default=None,
        description="Abstenciones / turnos atendidos (Ronda 93: los turnos fallidos no cuentan). "
        "`null` sin turnos atendidos.",
    )
    failed_turns: int = Field(default=0, description="Ronda 93: turnos con error técnico (action 'fallo').")
    failure_rate: Optional[float] = Field(default=None, description="Ronda 93: failed_turns / total_turns.")

    @classmethod
    def from_summary(cls, summary: ConversationMetricsSummary) -> "MetricsResponse":
        return cls(
            project_id=summary.project_id, since=summary.since, total_turns=summary.total_turns,
            turns_by_action=summary.turns_by_action, avg_latency_ms=summary.avg_latency_ms,
            p95_latency_ms=summary.p95_latency_ms, p99_latency_ms=summary.p99_latency_ms,
            abstention_rate=summary.abstention_rate, failed_turns=summary.failed_turns,
            failure_rate=summary.failure_rate,
        )


class QualityResponse(BaseModel):
    """GET /projects/{project_id}/quality (Ronda 59: roadmap de preparación
    RAG 3-5 -- el agente externo de pruebas de NEXOM y su tablero de doble
    validación necesitan poder leer estas métricas sin abrir la aplicación de
    escritorio). Capacidad administrativa opcional, de solo lectura,
    protegida por API key -- nunca por un token de widget, mismo criterio que
    /metrics: es información sobre la salud del proyecto, no algo que deba
    ver el visitante final de un sitio. Aditiva: no cambia nada de POST
    /messages ni de MessageResponse.

    Importante: estos datos se leen de project.db (el proyecto en edición
    activa, banco de pruebas de Calidad), no de la instantánea publicada que
    consume /messages -- si el proyecto sigue evolviendo después de publicar
    una instantánea, estos valores pueden no corresponder exactamente al
    contenido que un canal en producción está sirviendo en ese momento. Es el
    mismo comportamiento que ya tiene la pestaña de Calidad de la aplicación
    de escritorio, no una limitación nueva de este endpoint."""

    project_id: str
    has_complete_run: bool = Field(
        description="False si el proyecto todavía no tiene ninguna corrida de evaluación de "
        "alcance \"completa\" registrada -- todos los demás campos son `null` en ese caso.",
    )
    last_run_id: Optional[str] = None
    last_run_started_at: Optional[datetime] = None
    last_run_finished_at: Optional[datetime] = None
    overall_verdict: Optional[str] = Field(
        default=None,
        description="'verde' | 'amarillo' | 'rojo' | 'gris' -- el veredicto más severo entre los "
        "casos de la corrida (domain.quality.entities.EvaluationRun.overall_verdict).",
    )
    has_blocking_failures: Optional[bool] = None
    recall_at_3: Optional[float] = Field(
        default=None,
        description="`null` si ningún caso de la corrida declaró una fuente esperada -- mismo "
        "criterio de ausencia de dato que domain.quality.entities.EvaluationRun.recall_at_k.",
    )
    mrr: Optional[float] = Field(default=None, description="Mismas condiciones de `null` que recall_at_3.")
    regression_gate_passed: Optional[bool] = Field(
        default=None,
        description="Estado de la compuerta de liberación \"Regresión de recuperación\" (Ronda "
        "53) para la corrida más reciente -- True también cuando la compuerta se da por cumplida "
        "por falta de datos (menos de dos corridas \"completa\", o sin casos con fuente esperada), "
        "igual que en application/release/queries/evaluate_release_gates.py.",
    )
    regression_gate_reason: Optional[str] = None

    @classmethod
    def from_complete_runs(
        cls, project_id: str, complete_runs: list[EvaluationRun], regression_threshold: float,
    ) -> "QualityResponse":
        if not complete_runs:
            return cls(project_id=project_id, has_complete_run=False)
        current = complete_runs[0]
        fields: dict[str, Any] = dict(
            project_id=project_id, has_complete_run=True, last_run_id=current.id,
            last_run_started_at=current.started_at, last_run_finished_at=current.finished_at,
            overall_verdict=current.overall_verdict.value, has_blocking_failures=current.has_blocking_failures,
            recall_at_3=current.recall_at_k(3), mrr=current.mean_reciprocal_rank(),
        )
        if len(complete_runs) < 2:
            fields["regression_gate_passed"] = True
            fields["regression_gate_reason"] = (
                "Menos de dos corridas \"completa\" registradas todavía -- nada que comparar."
            )
            return cls(**fields)
        reference = complete_runs[1]
        current_recall, reference_recall = current.recall_at_k(3), reference.recall_at_k(3)
        if current_recall is None or reference_recall is None:
            fields["regression_gate_passed"] = True
            fields["regression_gate_reason"] = (
                "Ninguna de las dos corridas \"completa\" comparadas tiene casos con fuente "
                "esperada declarada -- no hay Recall@3/MRR que comparar."
            )
            return cls(**fields)
        current_mrr = current.mean_reciprocal_rank() or 0.0
        reference_mrr = reference.mean_reciprocal_rank() or 0.0
        worst_drop = max(
            relative_drop(reference_recall, current_recall), relative_drop(reference_mrr, current_mrr),
        )
        passed = worst_drop <= regression_threshold
        fields["regression_gate_passed"] = passed
        fields["regression_gate_reason"] = (
            f"Recall@3: {current_recall:.0%} (referencia: {reference_recall:.0%}), MRR: "
            f"{current_mrr:.2f} (referencia: {reference_mrr:.2f}) -- "
            + ("sin caída" if passed else "con caída")
            + f" por encima del umbral configurado ({regression_threshold:.0%})."
        )
        return cls(**fields)


_ACCESS_LEVEL_VALUES = ", ".join(f"'{nivel.value}'" for nivel in AccessLevel)


class IssueWidgetTokenRequest(BaseModel):
    """Cuerpo opcional de POST /projects/{id}/widget-tokens (Pista B.3
    del ADR-003, docs proyecto/RAG_STUDIO_Propuesta_B3_Control_Acceso.docx)
    -- deliberadamente con un único campo opcional para que una
    solicitud sin cuerpo (el comportamiento de siempre, ver
    GUIA_DESPLIEGUE.md de versiones anteriores) siga funcionando
    exactamente igual."""

    max_access_level: Optional[str] = Field(
        default=None,
        description=f"Techo de domain.documents.entities.AccessLevel que este canal tiene "
        f"autorizado ver ({_ACCESS_LEVEL_VALUES}). Si se omite, el token queda sin techo "
        "(\"restringido\" -- ve todo, igual que cualquier token emitido antes de esta capacidad).",
    )


class WidgetTokenResponse(BaseModel):
    """Solo se devuelve completo (con el valor real de `token`) al
    emitirlo -- ADR-002, Fase 4. Nunca se vuelve a mostrar después;
    quien lo pierda debe emitir uno nuevo y revocar el anterior."""

    id: str
    project_id: str
    token: str
    created_at: datetime
    max_access_level: str = Field(
        description="Pista B.3 del ADR-003 -- ver IssueWidgetTokenRequest.",
    )

    @classmethod
    def from_widget_token(cls, token: WidgetToken) -> "WidgetTokenResponse":
        return cls(
            id=token.id, project_id=token.project_id, token=token.token, created_at=token.created_at,
            max_access_level=token.max_access_level,
        )


class WidgetTokenSummary(BaseModel):
    """Vista para listar -- deliberadamente sin el valor real del
    token (ya se mostró una sola vez, al emitirlo)."""

    id: str
    project_id: str
    created_at: datetime
    revoked_at: Optional[datetime]
    is_active: bool
    max_access_level: str = Field(
        description="Pista B.3 del ADR-003 -- ver IssueWidgetTokenRequest.",
    )

    @classmethod
    def from_widget_token(cls, token: WidgetToken) -> "WidgetTokenSummary":
        return cls(
            id=token.id, project_id=token.project_id, created_at=token.created_at,
            revoked_at=token.revoked_at, is_active=token.is_active,
            max_access_level=token.max_access_level,
        )


_FEEDBACK_SIGNAL_VALUES = ", ".join(f"'{s.value}'" for s in FeedbackSignal)


class RetrievalFeedbackItemRequest(BaseModel):
    """Una señal sobre una fuente concreta -- source_id/chunk_id son
    exactamente los que MessageResponse.sources ya devolvió para el
    log_id de la URL; no hace falta ningún dato nuevo que el agente
    externo no tuviera ya (Pista C.4a del ADR-003, ver nota de cierre
    de RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx)."""

    source_id: str = Field(min_length=1, description="Uno de los source_id que este mismo turno ya mostró.")
    signal: str = Field(
        description=f"Una de {_FEEDBACK_SIGNAL_VALUES}. 'citado_en_respuesta' es la única señal de "
        "comportamiento (no un juicio) -- se usa cuando el agente externo de verdad se apoyó en esa "
        "fuente para construir su respuesta final, sin que eso implique juzgarla como correcta.",
    )
    chunk_id: Optional[str] = Field(
        default=None,
        description="Opcional, más preciso que source_id -- mismo chunk_id que ya viene en "
        "MessageResponse.sources para ese resultado.",
    )
    notes: Optional[str] = Field(default=None, max_length=500)


class RetrievalFeedbackRequest(BaseModel):
    entries: list[RetrievalFeedbackItemRequest] = Field(
        min_length=1,
        description="Una o más señales sobre fuentes de este mismo turno -- todas se registran, "
        "ninguna sustituye a una señal previa ya guardada (solo-inserción, ver nota de cierre de C.4a).",
    )


class RetrievalFeedbackResponse(BaseModel):
    recorded: int = Field(description="Cuántas señales se guardaron -- siempre len(entries) si no hubo error.")
