"""Entidades del contexto Runtime (ADR-002, Fase 2:
docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx).

`ConversationLogEntry` registra una conversación real atendida por
interfaces/api/ -- a diferencia de `SimulationTrace`
(application/conversational/queries/simulate_conversation.py), que es
el resultado de una prueba manual dentro del Simulador de la app de
escritorio y nunca se persiste. Existe para dos propósitos futuros
(fuera de alcance de esta fase, ver ADR-002 secciones 4 y 5):
monitorear el comportamiento real del agente, y alimentar el lazo de
retroalimentación hacia el banco de pruebas de calidad.

Ronda 19 (ver Validacion_observaciones_RAG_STUDIO.md, recomendación #1
de la evaluación de grado profesional -- Ronda 18): `ConversationLogEntry.
conversation_id` agrupa los turnos de una misma conversación del lado
del servidor. Antes de esta ronda no existía ningún campo así: cada
turno se guardaba de forma aislada, y la única forma de mantener
contexto entre mensajes era que el CANAL (el widget) reenviara
`variables` por su cuenta -- un integrador que no usara el widget (por
ejemplo, el backend propio de un agente conversacional externo que
llamara directamente a `POST /messages`) no tenía ningún concepto de
sesión que pedirle al servidor, ni la pestaña de Monitoreo podía
reconstruir "la conversación completa" de un visitante, solo turnos
sueltos. `HandleIncomingMessage` genera uno nuevo si quien llama no
manda ninguno (primer turno), y lo devuelve siempre en
`MessageResponse.conversation_id` -- reenviarlo en las siguientes
solicitudes es lo que agrupa los turnos.

`WidgetToken` y `ChannelingDispatch` son de la Fase 4
("endurecimiento operativo" + "canalización real"): el primero
resuelve el riesgo de seguridad documentado en la Fase 3 (incrustar la
`X-API-Key` operativa global en un `<script>` público solo era
aceptable para un piloto de un sitio de confianza); el segundo es la
traducción, hecha en `application/runtime` (nunca aquí), de un
`domain.conversational.ChannelingScheme` resuelto a datos planos --
`domain.runtime` sigue sin depender de `domain.conversational`, mismo
criterio que ya usa `ConversationLogEntry.action` (str, no el enum de
`domain.conversational`)."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from math import ceil
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


FAILED_ACTION = "fallo"
"""Ronda 93: `action` de un turno que no pudo atenderse por un error
técnico (además de responder/aclarar/abstenerse/canalizar). Antes estos
turnos no se guardaban."""


class ConversationLogEntry(BaseModel):
    """Un turno de conversación real: la pregunta recibida y la
    decisión que tomó el motor conversacional (mismo vocabulario de
    acción que `SimulationTrace.action`, pero aquí ya se resolvió
    contra una instantánea publicada, no contra el proyecto en
    edición)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """Agrupa los turnos de una misma conversación (Ronda 19). El
    default_factory es solo para quien construya la entidad directamente
    sin pensar en sesiones (pruebas, un turno aislado) -- en el camino
    real (`HandleIncomingMessage.execute`), el valor viene explícito:
    el que mandó el llamador, o uno recién generado si es el primer
    turno, nunca el default de este campo."""
    project_id: str
    snapshot_version: int
    """La versión de ProjectSnapshot (ADR-002, Fase 1) que respondió
    esta conversación -- trazabilidad de qué configuración exacta
    estaba vigente."""
    message: str
    matched_intent: Optional[str] = None
    confidence: Optional[float] = None
    action: str
    """Valor de RuleActionType ("responder"/"aclarar"/"abstenerse"/
    "canalizar") serializado como texto -- domain.runtime no depende
    de domain.conversational (ADR-001, sección 4: cada contexto
    conserva sus propios tipos; ver HandleIncomingMessage, que hace la
    conversión)."""
    response_text: Optional[str] = None
    source_ids: list[str] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    created_at: datetime = Field(default_factory=_utcnow)
    trace_id: Optional[str] = None
    """Ronda 93: identificador de correlación de la solicitud -- el que
    envió el consumidor en `X-Trace-Id` o uno generado por el runtime. Se
    devuelve en la respuesta (cuerpo y encabezado) y aparece en
    ragstudio-api.log. None en turnos guardados antes de esta ronda."""
    error_category: Optional[str] = None
    """Ronda 93: solo en turnos con action == FAILED_ACTION -- valor de
    `domain.runtime.failures.FailureCategory`. Nunca vacío en un fallo."""
    error_stage: Optional[str] = None
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    error_detail: Optional[str] = None
    """Tipo y mensaje de la excepción y cadena de llamadas (módulo:función:
    línea), sin valores de variables ni secretos."""
    chunk_ids: Optional[list[str]] = None
    """Ronda 104b (Etapa 0): fragmentos entregados, EN EL ORDEN de la
    respuesta (`source_ids` no conserva orden). None en filas anteriores."""
    execution: Optional[dict] = None
    """Ronda 104b (Etapa 0): datos de ejecución del turno (ver
    application/runtime/execution_info.py). None en filas anteriores o si
    quien construyó el motor no los proporcionó."""

    @property
    def failed(self) -> bool:
        return self.action == FAILED_ACTION


class ConversationMetricsSummary(BaseModel):
    """Resumen agregado sobre la bitácora de conversaciones reales de un
    proyecto (Pista C.1 del ADR-003 -- docs proyecto/
    RAG_STUDIO_Propuesta_C1_Observabilidad.docx): observabilidad básica
    calculada sobre datos que `ConversationLogEntry` ya persistía desde
    la Ronda 19 (`latency_ms`, `action`), sin ninguna columna ni tabla
    nueva. Quien lo construye (`ConversationLogRepository.
    get_metrics_summary`) agrega en SQL, nunca trae todas las filas a
    memoria para calcularlo -- ver infrastructure/database/
    runtime_repositories.py.

    Percentiles de latencia (p95/p99) agregados en la Ronda 44 (roadmap
    de pendientes de RAG 5, Pista C.5 del ADR-003): en la primera fase
    (Pista C.1) se pospusieron porque SQLite no tiene una función de
    percentil nativa sencilla y calcularlos en Python requeriría traer
    todas las latencias a memoria -- dado el volumen real de un
    proyecto de escritorio (un solo proyecto a la vez, turnos de un
    banco de pruebas o de un piloto, nunca millones de filas), se
    confirmó que traer solo la columna `latency_ms` (nunca la fila
    completa) a memoria es una alternativa aceptable; ver
    `latency_percentile` para el cálculo puro, compartido entre la
    implementación SQL real y el doble en memoria de pruebas."""

    project_id: str
    since: Optional[datetime] = None
    """Início de la ventana agregada -- `None` significa "todo el
    histórico del proyecto", no una fecha real. Nunca se confunde con
    un valor de verdad porque quien construye esta entidad (el
    repositorio) siempre pasa exactamente lo que recibió como
    parámetro `since`, sin normalizar `None` a ninguna fecha."""
    total_turns: int
    turns_by_action: dict[str, int] = Field(default_factory=dict)
    avg_latency_ms: Optional[float] = None
    """`None` cuando `total_turns == 0`, o cuando ningún turno de la
    ventana tiene `latency_ms` (fila histórica anterior a la captura
    de latencia) -- nunca 0.0, que sería un dato falso en vez de la
    ausencia de dato (mismo criterio que `EvaluationRun.recall_at_k`)."""
    p95_latency_ms: Optional[float] = None
    """Percentil 95 de `latency_ms` sobre los turnos de la ventana que
    sí tienen latencia capturada -- `None` en las mismas condiciones
    que `avg_latency_ms` (sin turnos, o ninguno con latencia). Calculado
    con `latency_percentile` (método de rango más cercano, sin
    dependencias externas)."""
    p99_latency_ms: Optional[float] = None
    """Percentil 99 de `latency_ms` -- mismo criterio que
    `p95_latency_ms`."""
    abstention_rate: Optional[float] = None
    """turns_by_action.get("abstenerse", 0) / turnos atendidos -- `None`
    cuando no hay turnos atendidos. Ronda 93: los turnos fallidos
    (`FAILED_ACTION`) no cuentan como atendidos, ni entran en las
    latencias: sin fallos, el valor es idéntico al de antes."""
    failed_turns: int = 0
    """Ronda 93: turnos que no pudieron atenderse (error técnico)."""
    failure_rate: Optional[float] = None
    """Ronda 93: failed_turns / total_turns; `None` sin turnos."""


def latency_percentile(latencies: list[float], percentile: float) -> Optional[float]:
    """Percentil puro (sin numpy ni dependencias externas), método de
    "rango más cercano" (nearest-rank): ordena `latencies` y devuelve
    el valor en la posición ceil(percentile/100 * n) -- 1-indexado,
    acotado a [1, n]. `None` con una lista vacía (mismo criterio que
    `avg_latency_ms`: ausencia de dato, no 0.0). Pensado para que la
    implementación SQL real (que trae solo la columna `latency_ms`, no
    filas completas) y el doble en memoria de pruebas compartan
    exactamente el mismo cálculo, en vez de reimplementarlo dos veces."""
    if not latencies:
        return None
    ordered = sorted(latencies)
    n = len(ordered)
    rank = max(1, min(n, ceil(percentile / 100 * n)))
    return ordered[rank - 1]


class FeedbackSignal(str, Enum):
    """Pista C.4a del ADR-003 (docs proyecto/
    RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx): lo que un
    humano (canal operador) o el agente conversacional externo (canal
    HTTP) reportan sobre una fuente concreta que se mostró en un turno
    real. RELEVANTE/IRRELEVANTE son juicios explícitos -- alguien
    evaluó la fuente y decidió. CITADO_EN_RESPUESTA es distinto: una
    señal de comportamiento, no un juicio -- el agente externo la usó
    de verdad al construir su respuesta final al usuario, sin que eso
    implique necesariamente que la evaluó como "correcta". Solo el
    agente externo puede reportar CITADO_EN_RESPUESTA (un operador
    humano revisando el panel de Monitoreo no tiene forma de saber qué
    citó el agente en la respuesta que el usuario final recibió)."""

    RELEVANTE = "relevante"
    IRRELEVANTE = "irrelevante"
    CITADO_EN_RESPUESTA = "citado_en_respuesta"


class FeedbackOrigin(str, Enum):
    """Quién registró la señal -- distinto de `signal` (qué dice la
    señal): permite, por ejemplo, contar cuántas señales vienen de
    revisión humana vs. del agente externo sin tener que inferirlo del
    valor de `signal`."""

    OPERADOR = "operador"
    AGENTE_EXTERNO = "agente_externo"


class RetrievalFeedbackEntry(BaseModel):
    """Una señal de relevancia sobre una fuente concreta mostrada en un
    turno real (Pista C.4a del ADR-003) -- la señal (b)/(c) del
    documento de decisión C.4; la señal (a) (curación humana explícita)
    sigue viviendo en `domain.quality.entities.TestCase`, sin cambios,
    y no se duplica aquí.

    Solo-inserción, deliberadamente (nota de cierre de C.4a, 2026-08-20):
    ninguna entrada se edita ni se borra una vez guardada -- mismo
    criterio que `EvaluationRun` (se conserva el historial completo de
    corridas) y la tabla `extraction_record_history` (preserva cada
    extracción anterior en vez de mutarla). Si alguien se equivoca,
    registra una entrada nueva sobre la misma fuente/turno; quien
    agregue estadísticas decide si le importa solo la más reciente por
    (conversation_log_entry_id, source_id) o el historial completo --
    esta entidad no impone ese criterio, solo lo hace posible."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    conversation_log_entry_id: str
    """Ancla al turno real (`ConversationLogEntry.id`) sobre el que se
    reporta esta señal -- ya se devuelve como `log_id` en
    `MessageResponse`, así que el agente conversacional externo no
    necesita que se le entregue ningún dato nuevo para poder usarlo."""
    source_id: str
    chunk_id: Optional[str] = None
    """Mejor esfuerzo: más preciso que `source_id`, pero más frágil si
    el chunk se vuelve a fragmentar (mismo riesgo de estabilidad ya
    documentado para `row_index` en la Pista C.2) -- `source_id` es el
    ancla estable, `chunk_id` es un detalle adicional cuando está
    disponible."""
    signal: FeedbackSignal
    origin: FeedbackOrigin
    notes: Optional[str] = None
    """Solo tiene sentido para origin=OPERADOR -- un agente externo no
    manda texto libre, solo la señal estructurada."""
    created_at: datetime = Field(default_factory=_utcnow)


class RetrievalFeedbackSummary(BaseModel):
    """Vista agregada de las señales de relevancia capturadas (Pista
    C.4a), pensada para juntarse en el panel de Monitoreo/Calidad junto
    con el tamaño del banco de pruebas (señal a) -- mismo criterio de
    agregación en SQL, nunca traer todas las filas a memoria, ya usado
    por `ConversationMetricsSummary`."""

    project_id: str
    since: Optional[datetime] = None
    total_entries: int
    counts_by_signal: dict[str, int] = Field(default_factory=dict)
    counts_by_origin: dict[str, int] = Field(default_factory=dict)


class WidgetToken(BaseModel):
    """Token público, acotado a un solo proyecto, para que el widget
    web (Fase 3) autentique al visitante final sin incrustar la
    `X-API-Key` operativa global -- de solo lectura conversacional (no
    puede emitir ni revocar otros tokens, ni acceder a otro
    project_id), y revocable en cualquier momento sin afectar la API
    key ni a otros proyectos."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    created_at: datetime = Field(default_factory=_utcnow)
    revoked_at: Optional[datetime] = None
    max_access_level: str = "restringido"
    """Pista B.3 del ADR-003 (docs proyecto/
    RAG_STUDIO_Propuesta_B3_Control_Acceso.docx): techo de
    `domain.documents.entities.AccessLevel` que este canal tiene
    autorizado ver -- "restringido" (el valor más PERMISIVO de ese
    Enum, no el más restrictivo pese al nombre del propio valor) es el
    default aquí a propósito, para que un token ya emitido antes de
    esta capacidad (o uno nuevo emitido sin especificar nada) siga
    viendo exactamente lo mismo que veía antes de que este campo
    existiera -- mismo criterio ya vigente en todo el proyecto para
    capacidades nuevas (only_usable_sources, rerank, expand_to_parent):
    por defecto, "apagado" en el sentido de "sin cambio de
    comportamiento". Es un `str`, no el Enum `AccessLevel`, a propósito:
    `domain.runtime` no depende de `domain.documents`, mismo criterio
    que ya usa `ConversationLogEntry.action` (str, no el enum de
    `domain.conversational`) -- ver docstring del módulo. Quien emite
    el token (application/runtime/commands/issue_widget_token.py)
    valida que el valor sea uno de los cuatro conocidos."""

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ReopeningCriteriaStatus(BaseModel):
    """Ronda 45 (RAG_STUDIO_Propuesta_Roadmap_RAG5_Pendientes.docx,
    sección 9, "Criterios de reapertura") fijó por escrito bajo qué
    condiciones reales valdría la pena reconsiderar dos pendientes de
    RAG 5 diferidos por falta de evidencia de uso real: alertas
    proactivas de observabilidad, y el ajuste automático del retrieval
    (aprendizaje, Opción 3). Verificar esas tres condiciones por cada
    pendiente exigía, hasta la Ronda 56, repetir una consulta SQL
    manual sobre el project.db/runtime.db real en cada ronda de
    consultoría (ver Rondas 43/45/50) -- esta entidad expone el
    resultado ya computado con el mismo criterio escrito en la Ronda
    45 (ver `application.runtime.queries.evaluate_reopening_criteria`),
    para que la propia aplicación lo muestre sin depender de que
    alguien recuerde repetir la consulta a mano.

    Cumplir los tres criterios de un pendiente NO obliga a construirlo
    -- solo señala que ya existe evidencia real suficiente para que
    valga la pena volver a preguntar (mismo matiz que ya deja explícito
    el documento de la Ronda 45). Campos planos (bool/int), no un Enum
    ni una referencia a `domain.projects.ProjectStatus` -- mismo
    criterio de desacoplamiento entre contextos que ya usa
    `WidgetToken.max_access_level` (str, no `AccessLevel`)."""

    project_id: str
    checked_at: datetime

    proyecto_liberado: bool
    """Condición 1 de "alertas proactivas": `Project.status ==
    ProjectStatus.LIBERADO` en el momento del chequeo."""
    token_widget_activo: bool
    """Condición 2 de "alertas proactivas": al menos un `WidgetToken`
    sin revocar (`is_active`) emitido para este proyecto."""
    turnos_ultimos_30_dias: int
    """Condición 3 de "alertas proactivas": turnos de
    `conversation_log` con `created_at` dentro de los últimos 30 días
    naturales desde `checked_at`."""
    alertas_proactivas_reunidas: bool
    """True solo si las tres condiciones anteriores se cumplen a la
    vez -- calculado por quien construye esta entidad, no una
    propiedad derivada, mismo criterio que `GateResult.passed`
    (domain.release.entities)."""

    entradas_feedback_totales: int
    """Condición 1 de "aprendizaje, Opción 3": total de filas de
    `retrieval_feedback` para este proyecto (todo el histórico, no una
    ventana)."""
    fuentes_distintas_en_feedback: int
    """Condición 2: cuántos `source_id` distintos aparecen entre esas
    entradas."""
    dias_desde_la_primera_entrada: Optional[int] = None
    """Condición 3 ("acumuladas en un período de uso real de al menos
    30 días naturales"): días transcurridos entre la entrada más
    antigua de `retrieval_feedback` y `checked_at` -- `None` si todavía
    no hay ninguna entrada. Es una aproximación honesta de "período de
    uso real" (mide la duración de la ventana de acumulación, no la
    continuidad día a día dentro de ella) -- el propio documento de la
    Ronda 45 ya aclaraba que estos tres números son "un punto de
    partida razonable, no una ley matemática"."""
    aprendizaje_opcion3_reunidas: bool
    """True solo si las tres condiciones de "aprendizaje, Opción 3" se
    cumplen a la vez."""


class ChannelingDispatch(BaseModel):
    """Datos planos de un evento de canalización real (Fase 4) --
    construidos por `HandleIncomingMessage` a partir de
    `SimulationTrace.channeling` (un `ChannelingScheme` de
    `domain.conversational`), nunca importado aquí."""

    project_id: str
    log_id: str
    message: str
    matched_intent: Optional[str] = None
    code: str
    name: str
    medium: str
    target_area: str = ""
    reason: str = ""
    user_message: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
