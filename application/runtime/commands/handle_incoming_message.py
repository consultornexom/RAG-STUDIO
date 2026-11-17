"""Caso de uso: atender un mensaje real de un canal (ADR-002, Fase 2 --
docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx). Reutiliza el
mismo motor de decisión que el Simulador (`ConversationalService.simulate`,
que a su vez llama a `SimulateConversation` -- no se reimplementa ninguna
lógica de intención/guardrails/búsqueda), pero:

1. Corre contra un `ConversationalService` construido sobre una
   instantánea publicada (ver `SnapshotInstallationPaths`), nunca
   contra el proyecto que la app de escritorio pueda estar editando.
2. Mide la latencia y persiste el resultado en `ConversationLogRepository`
   -- a diferencia del Simulador, que nunca guarda nada.

Nota deliberada sobre `response_text`: RAG STUDIO nunca implementó un
paso de generación de lenguaje natural (ADR-001, sección 8: "LLMProvider
... sin fijar; decisión de Etapa 5, local/externo por proyecto") -- ni
el Simulador ni este runtime "inventan" una respuesta a partir de los
fragmentos recuperados. Cuando la acción es RESPONDER, `response_text`
queda en None a propósito y el fragmento(s) recuperado(s) viajan en
`HandledMessage.trace.search_results` para que el canal (o una futura
integración de LLM, fuera de alcance de esta fase) decida qué mostrar.
Para ACLARAR/ABSTENERSE/CANALIZAR sí hay texto humano ya definido en el
propio diseño conversacional (pregunta aclaratoria, motivo de
abstención, mensaje de canalización) y se usa tal cual.

Ronda 19 (ver Validacion_observaciones_RAG_STUDIO.md): `execute` acepta
un `conversation_id` opcional -- si quien llama no manda ninguno (su
primer turno), se genera uno nuevo aquí mismo y viaja en
`HandledMessage.log_entry.conversation_id` para que `interfaces/api/`
lo devuelva siempre en la respuesta. Reenviarlo en las siguientes
solicitudes de la misma conversación es lo que le permite al servidor
agrupar los turnos (ver docstring de `domain.runtime.entities.
ConversationLogEntry`).

Canalización real (ADR-002, Fase 4): `channeling_dispatcher` es
opcional (mismo criterio que `RagService.embedding_provider_factory`)
-- sin configurar, CANALIZAR se comporta exactamente igual que en la
Fase 2 (solo el texto al usuario, nada más). Configurado, además
entrega el evento a un sistema externo real. La traducción de
`trace.channeling` (un `ChannelingScheme` de `domain.conversational`)
a `ChannelingDispatch` (datos planos de `domain.runtime`) ocurre aquí
a propósito: `domain.runtime` no depende de `domain.conversational`
(ADR-001, sección 4), igual que ya pasa con `action.value`. Un fallo
de entrega nunca debe romper la respuesta al visitante -- se captura,
nunca se relanza."""
from __future__ import annotations

import logging
import time
import uuid
from typing import NoReturn, Optional

from pydantic import BaseModel

from application.runtime.execution_info import execution_record, failure_execution_record
from application.conversational.queries.simulate_conversation import SimulationTrace
from application.conversational.service import ConversationalService
from domain.documents.entities import AccessLevel
from domain.runtime.entities import FAILED_ACTION, ChannelingDispatch, ConversationLogEntry
from domain.runtime.failures import FailureDiagnosis, FailureStage
from domain.runtime.ports import ChannelingDispatcher, ConversationLogRepository

from ..failure_diagnosis import diagnose_exception, format_traceback

logger = logging.getLogger(__name__)


class MessageHandlingFailedError(Exception):
    """Ronda 93: el motor no pudo atender el mensaje. Lleva el diagnóstico
    clasificado y, si se pudo guardar, el turno fallido de runtime.db
    (`log_entry`), para que la API responda con la causa en vez de un 500
    en texto plano."""

    def __init__(self, diagnosis: FailureDiagnosis, trace_id: str, log_entry: Optional[ConversationLogEntry]):
        super().__init__(diagnosis.summary)
        self.diagnosis = diagnosis
        self.trace_id = trace_id
        self.log_entry = log_entry


class HandledMessage(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    trace: SimulationTrace
    log_entry: ConversationLogEntry


class HandleIncomingMessage:
    def __init__(
        self, conversational_service: ConversationalService, log_repository: ConversationLogRepository,
        channeling_dispatcher: Optional[ChannelingDispatcher] = None,
        execution_base: Optional[dict] = None,
    ):
        """execution_base (Ronda 104b, Etapa 0): parte fija de los datos de
        ejecución (código, instantánea, índice) que se guarda con cada
        turno -- ver application/runtime/execution_info.py. Sin ella se
        registra igual el resto, marcando lo fijo como desconocido."""
        self._execution_base = execution_base
        self._conversational_service = conversational_service
        self._log_repository = log_repository
        self._channeling_dispatcher = channeling_dispatcher

    def execute(
        self, project_id: str, snapshot_version: int, message: str,
        provided_variables: Optional[dict[str, str]] = None, conversation_id: Optional[str] = None,
        max_access_level: Optional[AccessLevel] = None, auto_dispatch_channeling: bool = True,
        trace_id: Optional[str] = None,
    ) -> HandledMessage:
        """max_access_level (Pista B.3 del ADR-003, docs proyecto/
        RAG_STUDIO_Propuesta_B3_Control_Acceso.docx): techo de acceso
        del canal que autenticó esta solicitud -- interfaces/api/app.py
        lo resuelve a partir del WidgetToken (X-Widget-Token) o lo deja
        en None para la clave operativa global (X-API-Key), que sigue
        sin techo. Se reenvía tal cual a ConversationalService.simulate;
        None preserva el comportamiento de siempre.

        auto_dispatch_channeling (auditoría Ronda 46, hallazgo #146,
        corregido en la Ronda 51): por defecto True -- preserva el
        comportamiento de siempre (dispatch_channeling(), con sus
        reintentos y espera de `WebhookChannelingDispatcher`, ocurre
        aquí mismo, antes de devolver). `interfaces/api/app.py` lo pone
        en False y llama a `dispatch_channeling()` por separado
        DESPUÉS de soltar `loaded.lock` -- antes de esta corrección,
        ese lock (pensado solo para serializar el acceso a
        QdrantLocalVectorStore, ver LoadedSnapshot.lock) se quedaba
        tomado durante todo el reintento/espera del webhook saliente
        (hasta ~10.5s en el peor caso con la configuración por
        defecto), bloqueando sin necesidad a cualquier otro visitante
        de la MISMA instantánea mientras tanto. Ningún otro llamador de
        `execute()` (los tests unitarios existentes, en particular)
        necesita cambiar nada -- el valor por defecto sigue siendo el
        de siempre."""
        resolved_trace_id = trace_id or str(uuid.uuid4())
        resolved_conversation_id = conversation_id or str(uuid.uuid4())
        started = time.monotonic()
        try:
            trace = self._conversational_service.simulate(
                project_id, message, provided_variables, max_access_level=max_access_level,
            )
        except Exception as exc:  # noqa: BLE001 - se clasifica, se registra y se relanza (Ronda 93)
            self._record_failure(
                exc, project_id, snapshot_version, message, resolved_conversation_id, resolved_trace_id,
                (time.monotonic() - started) * 1000, FailureStage.MOTOR_CONVERSACIONAL,
            )
        latency_ms = (time.monotonic() - started) * 1000

        response_text = self._response_text_for(trace)
        source_ids = list({result.chunk.source_id for result in trace.search_results})

        # Ronda 19: el conversation_id (el del llamador o uno nuevo) se
        # resolvió arriba, antes de simular, para que también lo lleve un
        # turno fallido (Ronda 93).
        log_entry = ConversationLogEntry(
            project_id=project_id, conversation_id=resolved_conversation_id,
            snapshot_version=snapshot_version, message=message,
            # Ronda 10, hallazgo menor C11: `trace.confidence or None`
            # convertía una confianza legítima de 0.0 en None -- se
            # asigna tal cual, ya es Optional[float].
            matched_intent=trace.matched_intent_name, confidence=trace.confidence,
            action=trace.action.value, response_text=response_text, source_ids=source_ids,
            latency_ms=latency_ms, trace_id=resolved_trace_id,
            # Ronda 104b (Etapa 0): orden exacto entregado y datos de ejecución.
            chunk_ids=[result.chunk.id for result in trace.search_results],
            execution=execution_record(self._execution_base, trace),
        )
        try:
            self._log_repository.save(log_entry)
        except Exception as exc:  # noqa: BLE001 - Ronda 93: también se diagnostica el registro
            diagnosis = diagnose_exception(exc, FailureStage.REGISTRO_BITACORA)
            logger.error(
                "Turno atendido pero no registrado -- trace_id=%s categoria=%s etapa=%s codigo=%s\n%s",
                resolved_trace_id, diagnosis.category.value, diagnosis.stage.value, diagnosis.code,
                format_traceback(exc),
            )
            raise MessageHandlingFailedError(diagnosis, resolved_trace_id, None) from exc

        if auto_dispatch_channeling:
            self.dispatch_channeling(project_id, log_entry, trace)

        return HandledMessage(trace=trace, log_entry=log_entry)

    def dispatch_channeling(self, project_id: str, log_entry: ConversationLogEntry, trace: SimulationTrace) -> None:
        """Entrega el evento de canalización (si corresponde) al
        `ChannelingDispatcher` configurado. Público (antes,
        `_dispatch_channeling`, privado) para que `interfaces/api/
        app.py` pueda llamarlo explícitamente DESPUÉS de soltar
        `loaded.lock` cuando `execute()` se llamó con
        `auto_dispatch_channeling=False` -- ver docstring de
        `execute()`. Seguro de llamar siempre, sin condición previa:
        no hace nada si la acción no fue "canalizar", si no se resolvió
        ningún `ChannelingScheme`, o si no hay dispatcher configurado
        (mismos tres guardas que ya existían antes de esta ronda)."""
        if trace.action.value != "canalizar" or trace.channeling is None:
            return
        if self._channeling_dispatcher is None:
            return
        channeling = trace.channeling
        payload = ChannelingDispatch(
            project_id=project_id, log_id=log_entry.id, message=log_entry.message,
            matched_intent=trace.matched_intent_name, code=channeling.code, name=channeling.name,
            medium=channeling.medium.value, target_area=channeling.target_area, reason=channeling.reason,
            user_message=channeling.user_message,
        )
        try:
            self._channeling_dispatcher.dispatch(payload)
        except Exception:
            # A propósito: un canal externo caído no debe impedir que
            # el visitante reciba el mensaje de canalización que ya se
            # guardó en la bitácora -- ver docstring del módulo.
            logger.exception(
                "Fallo al entregar el evento de canalización %s del proyecto %s (log %s).",
                channeling.code, project_id, log_entry.id,
            )

    def _record_failure(
        self, exc: Exception, project_id: str, snapshot_version: int, message: str, conversation_id: str,
        trace_id: str, latency_ms: float, default_stage: FailureStage,
    ) -> NoReturn:
        """Clasifica la excepción, guarda el turno fallido (si runtime.db lo
        permite), deja la traza completa en el registro operativo con el
        mismo trace_id y relanza como MessageHandlingFailedError."""
        diagnosis = diagnose_exception(exc, default_stage)
        logger.error(
            "Turno fallido -- proyecto=%s version=%s trace_id=%s categoria=%s etapa=%s codigo=%s\n%s",
            project_id, snapshot_version, trace_id, diagnosis.category.value, diagnosis.stage.value,
            diagnosis.code, format_traceback(exc),
        )
        entry: Optional[ConversationLogEntry]
        entry = ConversationLogEntry(
            project_id=project_id, conversation_id=conversation_id, snapshot_version=snapshot_version,
            message=message, action=FAILED_ACTION, latency_ms=latency_ms, trace_id=trace_id,
            error_category=diagnosis.category.value, error_stage=diagnosis.stage.value,
            error_code=diagnosis.code, error_summary=diagnosis.summary, error_detail=diagnosis.technical_detail,
            execution=failure_execution_record(self._execution_base),
        )
        try:
            self._log_repository.save(entry)
        except Exception:  # noqa: BLE001 - el diagnóstico sigue viajando en la respuesta y en el log
            logger.exception("No se pudo guardar el turno fallido trace_id=%s en runtime.db.", trace_id)
            entry = None
        raise MessageHandlingFailedError(diagnosis, trace_id, entry) from exc

    @staticmethod
    def _response_text_for(trace: SimulationTrace) -> Optional[str]:
        if trace.action.value == "aclarar":
            return trace.clarifying_question
        if trace.action.value == "abstenerse":
            return trace.abstention_reason
        if trace.action.value == "canalizar":
            return trace.channeling.user_message if trace.channeling else None
        return None  # "responder": ver nota del módulo -- no hay paso de generación de lenguaje natural.
