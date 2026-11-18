"""Servicio HTTP mínimo del runtime de producción (ADR-002, Fase 2).

Uso en desarrollo/pruebas -- construir una instancia apuntada a una
instalación concreta:

    from interfaces.api.app import create_app
    app = create_app(installation_dir="/ruta/a/agent_studio")

Para desplegar (`uvicorn interfaces.api.app:app`), la instalación y el
perfil de embeddings se resuelven de las mismas variables de entorno
que ya usa la app de escritorio (RAGSTUDIO_HOME,
RAGSTUDIO_EMBEDDING_PROFILE -- ver app/configuration.py), más
RAGSTUDIO_API_KEY (obligatoria: sin ella el proceso no arranca, para
no exponer por accidente un runtime sin autenticación) y, opcional,
RAGSTUDIO_RUNTIME_DB_PATH (por defecto, runtime.db dentro de la
instalación).

Requiere el extra `api` (`pip install -e .[api]`) -- no es una
dependencia de la app de escritorio.

Fase 3 (ADR-002, "primer canal real"): agrega el widget web embebible
servido en `GET /widget.js` (ver docstring de `widget_assets.py` para
el diseño completo) y CORS configurable -- sin él, ningún navegador
deja que el widget, embebido en el sitio de un cliente, llame a este
servicio desde otro origen. CORS queda desactivado por defecto (mismo
criterio que la API key: sin configurar, el servicio se comporta como
antes de esta fase); se activa con `allowed_origins` (o la variable de
entorno RAGSTUDIO_WIDGET_ALLOWED_ORIGINS, orígenes separados por
coma) -- solo para el/los orígenes del sitio donde se embeba el
widget, nunca "*" en un despliegue real con API key configurada (ver
widget_assets.py sobre por qué la API key no debe tratarse como un
secreto público).

Fase 4 (ADR-002, "endurecimiento operativo" + "canalización real"):
1. Token de widget por proyecto (`WidgetToken`) -- resuelve el riesgo
   documentado en la Fase 3. `POST /projects/{id}/widget-tokens`
   (protegido por la API key global, nunca por un token de widget)
   emite uno nuevo; `GET` lista los existentes (sin el valor real,
   solo se muestra completo al emitirlo); `DELETE .../{token_id}` lo
   revoca. `POST /projects/{id}/messages` ahora acepta *o* la API key
   global (uso administrativo/piloto de un solo sitio) *o* un token de
   widget válido para ESE proyecto (`X-Widget-Token`) -- nunca un
   token de otro proyecto.
2. Canalización real vía webhook saliente (opcional, ver
   `infrastructure/channeling/webhook_dispatcher.py`) -- configurable
   con `RAGSTUDIO_CHANNELING_WEBHOOK_URL` y, opcional,
   `RAGSTUDIO_CHANNELING_WEBHOOK_SECRET`. Sin configurar, CANALIZAR se
   comporta exactamente igual que en la Fase 2 (solo el texto al
   usuario). El secreto se lee de una variable de entorno -- no de
   `infrastructure/security/keyring_credential_store.py` -- a
   propósito: ese almacén está pensado para credenciales de plugins de
   la app de ESCRITORIO (respaldado por el Secret Service/Keychain del
   usuario que la tiene abierta) y degrada mal en un proceso de
   SERVIDOR headless (sin sesión de escritorio); la inyección de
   secretos por variable de entorno es el mecanismo estándar para
   procesos de servidor (Docker/Kubernetes secrets, Vault, etc.), no
   un atajo -- es la práctica correcta para este caso, no la misma
   preocupada por la que se abandonó reforzar keyring aquí.

Ronda 10 (auditoría posterior a las 5 fases, ver
Validacion_observaciones_RAG_STUDIO.md, hallazgos A3/A4/B1/A2):

- RAGSTUDIO_SNAPSHOT_DIR (opcional): si se configura, este proceso
  sirve SIEMPRE esa instantánea exacta (una ruta a un directorio con
  project.db + índice Qdrant, típicamente la carpeta `instantanea/`
  de un paquete de entrega al cliente -- ver `GUIA_DESPLIEGUE.md`
  generado por "Exportar paquete de entrega al cliente…") en vez de
  consultar el registro de instantáneas de `RAGSTUDIO_HOME` (que vive
  en `projects/<project_id>/project.db`, el que la app de escritorio
  sigue editando, y que un paquete de entrega no incluye). Sin esta
  variable, el comportamiento es el de siempre: se sirve la última
  instantánea publicada según ese registro, y puede cambiar sin aviso
  si se publica una nueva mientras este proceso corre. Con ella
  configurada, la instantánea queda de verdad fija (RAGSTUDIO_HOME ya
  no necesita apuntar a ninguna instalación de escritorio real).
  RAGSTUDIO_SNAPSHOT_VERSION identifica la versión en la bitácora y
  en `/health`. Ronda 92: ya NO tiene valor por defecto; la versión se
  deriva de `instantanea/snapshot_identity.json` (o del manifest.json
  del paquete) y la variable, si se define, debe coincidir -- ver
  runtime_config.py.
- Si el directorio resuelto (fijado o del registro) no contiene un
  `project.db`, `POST /projects/{id}/messages` responde 404 con un
  mensaje explícito en vez de crear en silencio un proyecto vacío
  (antes de esta ronda, eso era lo que pasaba: `ensure_project_db`
  crea y migra un `project.db` nuevo si no encuentra uno).
- Cada instantánea cargada sirve sus mensajes bajo un lock propio
  (`LoadedSnapshot.lock`, ver runtime_context.py): dos visitantes
  concurrentes de la MISMA instantánea ya no chocan contra el lock
  exclusivo que `QdrantClient(path=...)` toma por apertura (antes de
  esta ronda, la segunda solicitud simultánea fallaba con un 500).
  Instantáneas distintas (proyectos o versiones distintos) siguen
  atendiéndose en paralelo -- solo se serializa lo que de verdad
  comparte el mismo directorio de índice.

Ronda 11 (cierre de brechas de "grado profesional" identificadas al
analizar el entregable al cliente, ver
Validacion_observaciones_RAG_STUDIO.md):

- Registro operativo real: `create_app_from_env` ahora llama a
  `app.logging_setup.configure_logging` (el mismo mecanismo que ya
  usa la app de escritorio, con redacción de credenciales) -- antes de
  esta ronda, el proceso no configuraba ningún logging propio, así que
  los `logger.info`/`logger.exception` que ya existían en el código
  (por ejemplo, en `handle_incoming_message.py` para fallos del
  webhook de canalización) no llegaban a ningún archivo. De paso se
  corrigió un defecto real en `configure_logging` mismo (afectaba
  también a la app de escritorio, no solo a este runtime): adjuntaba
  los handlers a un logger con nombre propio en vez del logger raíz,
  así que ningún `logging.getLogger(__name__)` de ningún módulo
  llegaba nunca al archivo -- ver docstring de `app/logging_setup.py`.
  Se escribe en `ragstudio-api.log` (no `ragstudio.log`, para no
  competir con la app de escritorio si comparten `RAGSTUDIO_HOME`),
  dentro de `RAGSTUDIO_HOME/logs/`. Nivel configurable con
  RAGSTUDIO_LOG_LEVEL (por defecto INFO). Deliberadamente NUNCA se
  registra el texto de los mensajes de los visitantes en este log --
  eso ya vive, estructurado, en `runtime.db` (ver pestaña Monitoreo,
  con su propio ciclo de vida); este log es para diagnosticar el
  servicio, no para duplicar la bitácora de negocio.
- Límite de tasa opcional en `POST /messages` (ver `rate_limiting.py`):
  RAGSTUDIO_RATE_LIMIT_PER_MINUTE, apagado por defecto (mismo criterio
  que la API key y CORS). Por IP del visitante, ventana deslizante en
  memoria de un minuto -- responde 429 con `Retry-After` al exceder.
  Protege la capacidad de ESTE proceso; no sustituye un límite de tasa
  a nivel de reverse proxy/CDN si el volumen esperado lo justifica.

Para producción, arrancar con el factory de `create_app_from_env` en
vez de depender del `app` a nivel de módulo (ver más abajo por qué):

    uvicorn interfaces.api.app:create_app_from_env --factory
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.logging_setup import configure_logging
from application.runtime.commands.handle_incoming_message import HandleIncomingMessage, MessageHandlingFailedError
from application.runtime.failure_diagnosis import diagnose_exception, format_traceback
from application.runtime.commands.issue_widget_token import IssueWidgetToken
from application.runtime.commands.record_retrieval_feedback import (
    ConversationLogEntryNotFoundError,
    RecordRetrievalFeedback,
)
from application.runtime.commands.revoke_widget_token import RevokeWidgetToken, WidgetTokenNotFoundError
from application.runtime.queries.list_widget_tokens import ListWidgetTokens
from application.quality.options import DEFAULT_QUALITY_REGRESSION_THRESHOLD
from application.quality.queries.list_complete_evaluation_runs import ListCompleteEvaluationRuns
from domain.documents.entities import AccessLevel
from domain.projects.exceptions import ProjectNotFoundError
from domain.runtime.entities import FAILED_ACTION, ConversationLogEntry, FeedbackOrigin, FeedbackSignal
from domain.runtime.failures import FailureCategory, FailureDiagnosis, FailureStage
from domain.runtime.ports import ChannelingDispatcher
from infrastructure.channeling.webhook_dispatcher import WebhookChannelingDispatcher
from infrastructure.database.quality_repositories import SqlAlchemyEvaluationRunRepository
from infrastructure.database.repositories import SqlAlchemyProjectRepository
from infrastructure.database.runtime_repositories import (
    SqlAlchemyConversationLogRepository,
    SqlAlchemyRetrievalFeedbackRepository,
    SqlAlchemyWidgetTokenRepository,
)
from infrastructure.filesystem.paths import InstallationPaths

from .rate_limiting import RateLimiter
from .runtime_config import LEGACY_API_KEY_VARS, load_runtime_config
from .runtime_context import (
    EmbeddingProviderFactory, ImageEmbeddingProviderFactory, RuntimeContext, SnapshotNotFoundError,
)
from application.conversational.queries.simulate_conversation import RETRIEVAL_PIPELINE
from infrastructure.build_info import current_code_identity
from .schemas import (
    ErrorInfo, ErrorResponse, ExecutionCode, HealthDetailsResponse, HealthResponse, IssueWidgetTokenRequest, MessageRequest, MessageResponse, MetricsResponse,
    QualityResponse, RetrievalFeedbackRequest, RetrievalFeedbackResponse, WidgetTokenResponse,
    WidgetTokenSummary,
)
from .widget_assets import WIDGET_JS

logger = logging.getLogger(__name__)

# Ruff B008 ("no llamar funciones en defaults de argumentos") prohibe
# `IssueWidgetTokenRequest()` directamente como default de parámetro
# más abajo (issue_widget_token) -- este singleton de módulo es la
# corrección que la propia regla sugiere en su mensaje ("read the
# default from a module-level singleton variable"). Seguro de
# compartir: nada lo muta in-place, solo se leen sus campos.
_DEFAULT_ISSUE_WIDGET_TOKEN_REQUEST = IssueWidgetTokenRequest()


_TRACE_ID_VALIDO = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")
_CATEGORIAS_REINTENTABLES = {FailureCategory.TIMEOUT, FailureCategory.STORAGE}


def _sanear_trace_id(valor: Optional[str]) -> str:
    """Ronda 93: usa el X-Trace-Id del consumidor si es un identificador
    razonable (evita inyectar texto arbitrario en el registro); si no, uno nuevo."""
    valor = (valor or "").strip()
    return valor if _TRACE_ID_VALIDO.match(valor) else str(uuid.uuid4())


class _DiagnosedHTTPError(Exception):
    """Ronda 93: error HTTP con diagnóstico estructurado (ErrorResponse)."""

    def __init__(
        self, status_code: int, diagnosis: FailureDiagnosis, trace_id: str,
        log_id: Optional[str] = None, snapshot_version: Optional[int] = None,
    ):
        super().__init__(diagnosis.summary)
        self.status_code = status_code
        self.diagnosis = diagnosis
        self.trace_id = trace_id
        self.log_id = log_id
        self.snapshot_version = snapshot_version

    def to_response(self) -> JSONResponse:
        d = self.diagnosis
        cuerpo = ErrorResponse(
            detail=d.summary,
            error=ErrorInfo(
                category=d.category.value, stage=d.stage.value, code=d.code, message=d.summary,
                trace_id=self.trace_id, log_id=self.log_id, snapshot_version=self.snapshot_version,
                exception_type=d.exception_type, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                retryable=d.category in _CATEGORIAS_REINTENTABLES or d.code == "retrieval.index_locked",
            ),
        )
        return JSONResponse(
            status_code=self.status_code, content=cuerpo.model_dump(), headers={"X-Trace-Id": self.trace_id},
        )


def create_app(
    installation_dir: str | Path, embedding_profile: str = "simetrico",
    api_key: Optional[str] = None, runtime_db_path: Optional[str | Path] = None,
    embedding_provider_factory: Optional[EmbeddingProviderFactory] = None,
    image_embedding_provider_factory: Optional[ImageEmbeddingProviderFactory] = None,
    allowed_origins: Optional[list[str]] = None,
    channeling_dispatcher: Optional[ChannelingDispatcher] = None,
    pinned_snapshot_dir: Optional[str | Path] = None, pinned_snapshot_version: Optional[int] = None,
    rate_limit_per_minute: Optional[int] = None, pinned_project_id: Optional[str] = None,
    reranker_factory=None,
) -> FastAPI:
    installation_dir = Path(installation_dir)
    runtime_context = RuntimeContext(
        installation_dir, embedding_profile=embedding_profile,
        embedding_provider_factory=embedding_provider_factory,
        image_embedding_provider_factory=image_embedding_provider_factory,
        pinned_snapshot_dir=pinned_snapshot_dir, pinned_snapshot_version=pinned_snapshot_version,
        pinned_project_id=pinned_project_id, reranker_factory=reranker_factory,
    )
    resolved_runtime_db_path = (
        runtime_db_path if runtime_db_path is not None else InstallationPaths(installation_dir).runtime_db_path()
    )
    log_repository = SqlAlchemyConversationLogRepository(resolved_runtime_db_path)
    widget_token_repository = SqlAlchemyWidgetTokenRepository(resolved_runtime_db_path)
    # feedback_repository (Pista C.4a del ADR-003, docs proyecto/
    # RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx): mismo
    # runtime.db, tabla nueva -- habilita el canal del agente
    # conversacional externo (POST /projects/{id}/messages/{log_id}/
    # feedback, más abajo).
    feedback_repository = SqlAlchemyRetrievalFeedbackRepository(resolved_runtime_db_path)
    record_feedback = RecordRetrievalFeedback(log_repository, feedback_repository)
    rate_limiter = RateLimiter(rate_limit_per_minute) if rate_limit_per_minute else None
    # evaluation_run_repository/project_repository (Ronda 59, roadmap de
    # preparación RAG 3-5): GET /projects/{id}/quality, más abajo. Leen
    # project.db (el mismo que abre la app de escritorio), no
    # runtime_db_path -- ver docstring de QualityResponse sobre por qué
    # esto puede no coincidir con la instantánea publicada.
    installation_paths = InstallationPaths(installation_dir)
    evaluation_run_repository = SqlAlchemyEvaluationRunRepository(installation_paths)
    project_repository = SqlAlchemyProjectRepository(installation_paths)
    list_complete_evaluation_runs = ListCompleteEvaluationRuns(evaluation_run_repository)

    app = FastAPI(
        title="RAG STUDIO -- Runtime de producción",
        description="ADR-002, Fase 2/3/4: expone el motor conversacional ya construido a un canal real.",
        version="0.1.0",
    )

    if allowed_origins:
        # Solo afecta a las respuestas del navegador -- no es control de
        # acceso (eso sigue siendo la API key, cuando está configurada);
        # es lo que le permite al navegador de un visitante leer la
        # respuesta cuando el widget corre en el origen del sitio que lo
        # embebió, distinto del origen de este servicio.
        app.add_middleware(
            CORSMiddleware, allow_origins=allowed_origins, allow_methods=["POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-API-Key", "X-Widget-Token", "X-Trace-Id"],
            # Ronda 93: que un consumidor en navegador pueda leer el trace_id.
            expose_headers=["X-Trace-Id"],
        )

    def _require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        if api_key is None:
            return  # Sin API key configurada -- solo para pruebas locales; ver create_app_from_env.
        # secrets.compare_digest (auditoría Ronda 10, hallazgo menor C2):
        # comparación en tiempo constante -- `!=` sobre str filtra por
        # temporización cuánto prefijo coincide. El ruido de red domina
        # sobre localhost, pero no cuesta nada evitarlo.
        if x_api_key is None or not secrets.compare_digest(x_api_key, api_key):
            logger.warning("Acceso administrativo rechazado: API key inválida o ausente.")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="API key inválida o ausente.")

    def _require_message_auth(
        project_id: str, x_api_key: Optional[str] = Header(default=None),
        x_widget_token: Optional[str] = Header(default=None),
    ) -> Optional[AccessLevel]:
        # Pista B.3 del ADR-003 (docs proyecto/
        # RAG_STUDIO_Propuesta_B3_Control_Acceso.docx): el techo de
        # acceso viaja con la CREDENCIAL que autentica la solicitud, no
        # con un campo del cuerpo del mensaje -- ni CONTRATO_INTEGRACION.md
        # ni MessageRequest ganan ningún campo nuevo. El valor devuelto
        # (None = sin techo) es lo que post_message reenvía a
        # HandleIncomingMessage.
        if api_key is None:
            return None  # Sin API key configurada -- solo para pruebas locales; ver create_app_from_env.
        if x_api_key is not None and secrets.compare_digest(x_api_key, api_key):
            # Acceso administrativo/piloto de un solo sitio (Fase 3):
            # deliberadamente sin techo, mismo criterio ya documentado
            # en GUIA_DESPLIEGUE.md para esta credencial.
            return None
        if x_widget_token is not None:
            token = widget_token_repository.get_by_token(x_widget_token)
            if token is not None and token.is_active and token.project_id == project_id:
                # Acceso acotado a este proyecto vía el widget (Fase 4)
                # -- AccessLevel(...) nunca debería fallar aquí: el
                # único punto de entrada que persiste este campo
                # (IssueWidgetToken.execute) ya valida contra el mismo
                # Enum antes de guardar.
                return AccessLevel(token.max_access_level)
        logger.warning("Acceso a mensajes rechazado para el proyecto %s: credencial inválida o ausente.", project_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="API key o token de widget inválido o ausente.")

    def _enforce_rate_limit(request: Request) -> None:
        # Ronda 11 (ver Validacion_observaciones_RAG_STUDIO.md): opt-in,
        # apagado por defecto -- mismo criterio que la API key y CORS
        # (sin configurar, se comporta igual que antes de esta ronda).
        # Por IP del visitante, antes de resolver si la credencial es
        # válida: protege la capacidad del proceso contra CUALQUIER
        # origen que mande tráfico excesivo, no solo contra quien ya
        # tiene un token válido (ver rate_limiting.py sobre por qué).
        if rate_limiter is None:
            return
        client_key = request.client.host if request.client is not None else "desconocido"
        if not rate_limiter.allow(client_key):
            logger.warning("Límite de tasa excedido para %s en %s.", client_key, request.url.path)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas solicitudes. Intenta de nuevo en unos segundos.",
                headers={"Retry-After": str(rate_limiter.retry_after_seconds(client_key))},
            )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        pinned = runtime_context.pinned_identity()
        return HealthResponse(
            status="ok", loaded_projects=runtime_context.loaded_project_ids(),
            snapshot_mode="fija" if pinned else "registro",
            snapshot_project_id=pinned[0] if pinned else None,
            snapshot_version=pinned[1] if pinned else None,
            embedding_profile=embedding_profile,
            # Ronda 104b (Etapa 0): solo datos no sensibles en el endpoint
            # público; el commit y las huellas van en /health/details.
            code_version=current_code_identity().version,
            retrieval_pipeline=RETRIEVAL_PIPELINE,
        )

    @app.get("/health/details", response_model=HealthDetailsResponse, dependencies=[Depends(_require_api_key)])
    def health_details() -> HealthDetailsResponse:
        """Ronda 104b (Etapa 0): detalles internos del despliegue para
        reproducir trazas -- protegido con la clave operativa."""
        identidad = current_code_identity()
        bases = runtime_context.loaded_execution_bases()
        reranking = bases[0].get("reranking", {}) if bases else {}
        return HealthDetailsResponse(
            code=ExecutionCode(**identidad.to_dict()), retrieval_pipeline=RETRIEVAL_PIPELINE,
            snapshot_mode="fija" if runtime_context.pinned_identity() else "registro",
            embedding_profile=embedding_profile,
            reranking_model_available=reranking.get("model_available") if bases else None,
            reranking_available_model=reranking.get("available_model"),
            pinned_snapshot=runtime_context.pinned_snapshot_description(),
            loaded_snapshots=[
                {"snapshot": base.get("snapshot"), "index": base.get("index"), "reranking": base.get("reranking")}
                for base in bases
            ],
            package_fingerprints=identidad.package_dict(),
        )

    @app.get(
        "/projects/{project_id}/metrics", response_model=MetricsResponse,
        dependencies=[Depends(_require_api_key)],
    )
    def get_metrics(project_id: str, since: Optional[datetime] = None) -> MetricsResponse:
        # Pista C.1 del ADR-003 (docs proyecto/
        # RAG_STUDIO_Propuesta_C1_Observabilidad.docx) -- observabilidad
        # básica: capacidad administrativa opcional (C.1c), protegida
        # SOLO por la API key global, nunca por un token de widget --
        # mismo criterio que /projects/{id}/widget-tokens, no
        # /projects/{id}/messages. Lee directo de log_repository (la
        # misma instancia que ya escribe post_message más abajo) -- no
        # se construye ningún RuntimeMonitoringService aquí porque este
        # endpoint no necesita el resto de esa fachada (promover a caso
        # de prueba, purgar) y esa fachada exige un TestCaseRepository
        # que este proceso no tiene ninguna razón para abrir.
        summary = log_repository.get_metrics_summary(project_id, since=since)
        return MetricsResponse.from_summary(summary)

    @app.get(
        "/projects/{project_id}/quality", response_model=QualityResponse,
        dependencies=[Depends(_require_api_key)],
    )
    def get_quality(project_id: str) -> QualityResponse:
        # Ronda 59 (roadmap de preparación RAG 3-5): capacidad
        # administrativa opcional, de solo lectura, protegida SOLO por
        # la API key global -- mismo criterio que /metrics, nunca un
        # token de widget. Reutiliza ListCompleteEvaluationRuns
        # (application/quality/, ya construida para la compuerta de
        # liberación "Regresión de recuperación" y la vista de
        # tendencia de la UI) y la función pura relative_drop del
        # dominio -- sin instanciar EvaluateReleaseGates ni las otras 6
        # compuertas, que este endpoint no necesita.
        complete_runs = list_complete_evaluation_runs.execute(project_id)
        project = project_repository.get(project_id)
        threshold = (
            project.quality_regression_threshold
            if project is not None and project.quality_regression_threshold is not None
            else DEFAULT_QUALITY_REGRESSION_THRESHOLD
        )
        return QualityResponse.from_complete_runs(project_id, complete_runs, threshold)

    @app.get("/widget.js")
    def widget_js() -> Response:
        # Público a propósito -- es el mismo archivo que cualquier
        # sitio que embeba el widget debe poder descargar sin
        # autenticación (ver widget_assets.py); no expone ningún dato
        # de negocio, solo el código del cliente.
        # charset explícito (auditoría Ronda 10, hallazgo menor C4):
        # Starlette solo agrega "charset=utf-8" a media types "text/*";
        # sin esto, el navegador decodifica este JS (que trae "💬"/"…")
        # con la codificación de la página anfitriona, no UTF-8.
        return Response(content=WIDGET_JS, media_type="application/javascript; charset=utf-8")

    @app.post(
        "/projects/{project_id}/widget-tokens", response_model=WidgetTokenResponse,
        dependencies=[Depends(_require_api_key)],
    )
    def issue_widget_token(
        project_id: str, request: IssueWidgetTokenRequest = _DEFAULT_ISSUE_WIDGET_TOKEN_REQUEST,
    ) -> WidgetTokenResponse:
        # Solo con la API key global -- un token de widget nunca debe
        # poder emitir ni ver otros tokens (eso anularía el acotamiento
        # por proyecto que es la razón de ser de esta fase). `request`
        # con default (Pista B.3): una solicitud sin cuerpo -- el
        # comportamiento de siempre -- sigue funcionando igual, ver
        # IssueWidgetTokenRequest. El default es el singleton de
        # módulo _DEFAULT_ISSUE_WIDGET_TOKEN_REQUEST (no una llamada
        # aquí mismo) por Ruff B008 -- ver comentario junto al logger.
        try:
            token = IssueWidgetToken(widget_token_repository).execute(
                project_id, max_access_level=request.max_access_level,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return WidgetTokenResponse.from_widget_token(token)

    @app.get(
        "/projects/{project_id}/widget-tokens", response_model=list[WidgetTokenSummary],
        dependencies=[Depends(_require_api_key)],
    )
    def list_widget_tokens_endpoint(project_id: str) -> list[WidgetTokenSummary]:
        tokens = ListWidgetTokens(widget_token_repository).execute(project_id)
        return [WidgetTokenSummary.from_widget_token(token) for token in tokens]

    @app.delete(
        "/projects/{project_id}/widget-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(_require_api_key)],
    )
    def revoke_widget_token_endpoint(project_id: str, token_id: str) -> None:
        try:
            token = widget_token_repository.get_by_id(token_id)
            if token is None or token.project_id != project_id:
                raise WidgetTokenNotFoundError(token_id)
            RevokeWidgetToken(widget_token_repository).execute(token_id)
        except WidgetTokenNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    def _guardar_fallo(
        project_id: str, snapshot_version: int, request: MessageRequest, trace_id: str,
        diagnosis: FailureDiagnosis,
    ) -> Optional[str]:
        """Ronda 93: guarda en runtime.db un turno fallido ocurrido antes de
        llegar al motor (p. ej. al cargar la instantánea)."""
        entry = ConversationLogEntry(
            project_id=project_id, conversation_id=request.conversation_id or str(uuid.uuid4()),
            snapshot_version=snapshot_version, message=request.message, action=FAILED_ACTION,
            trace_id=trace_id, error_category=diagnosis.category.value, error_stage=diagnosis.stage.value,
            error_code=diagnosis.code, error_summary=diagnosis.summary, error_detail=diagnosis.technical_detail,
        )
        try:
            log_repository.save(entry)
        except Exception:  # noqa: BLE001 - el diagnóstico sigue viajando en la respuesta y en el log
            logger.exception("No se pudo guardar el turno fallido trace_id=%s en runtime.db.", trace_id)
            return None
        return entry.id

    @app.post(
        "/projects/{project_id}/messages", response_model=MessageResponse,
        dependencies=[Depends(_enforce_rate_limit)],
    )
    def post_message(
        project_id: str, request: MessageRequest, response: Response,
        max_access_level: Optional[AccessLevel] = Depends(_require_message_auth),
        x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
        x_api_key: Optional[str] = Header(default=None),
    ) -> MessageResponse:
        # max_access_level (Pista B.3 del ADR-003): _require_message_auth
        # ya no solo autentica -- también resuelve el techo de acceso de
        # la credencial usada (None para X-API-Key, el de WidgetToken
        # para X-Widget-Token), así que se saca de `dependencies=[...]`
        # (donde el valor de retorno se descarta) a un parámetro normal.
        #
        # IMPORTANTE (se intentó y se revirtió durante esta misma ronda):
        # NO envolver `Depends(_require_message_auth)` en
        # `Annotated[...]` para "resolver" el B008 de Ruff más abajo --
        # este módulo tiene `from __future__ import annotations`
        # (encabezado del archivo), que convierte TODAS las anotaciones
        # de tipo en texto sin evaluar hasta que algo las resuelve.
        # FastAPI resuelve esas cadenas con `typing.get_type_hints()`
        # usando los GLOBALS del módulo -- pero `_require_message_auth`
        # es una variable LOCAL de esta función (`create_app`), no del
        # módulo, así que dentro de un `Annotated[...]` como anotación
        # de tipo, FastAPI nunca la encuentra y el endpoint queda SIN
        # autenticar de verdad (se comprobó real: 0 llamadas a
        # `_require_message_auth`, cualquier credencial o ninguna
        # pasaba, y el único error visible era el 404 de "sin
        # instantánea", nunca un 401) -- un hallazgo serio que no debe
        # repetirse. Como DEFAULT del parámetro (no como anotación),
        # `Depends(...)` se evalúa de inmediato al definir la función
        # (el `from __future__ import annotations` no afecta a los
        # valores default, solo a las anotaciones), así que la
        # referencia a la variable local se resuelve correctamente en
        # ese momento -- éste es el motivo real por el que este patrón
        # debe seguir así. El B008 de Ruff para este caso exacto se
        # silencia en pyproject.toml (`extend-immutable-calls`), no
        # reestructurando el código.
        # Ronda 93: identificador de correlación (el del consumidor si lo
        # manda, p. ej. el Trace ID de NEXOM Testing Agent).
        trace_id = _sanear_trace_id(x_trace_id)
        response.headers["X-Trace-Id"] = trace_id
        try:
            loaded = runtime_context.get_latest(project_id)
        except (SnapshotNotFoundError, ProjectNotFoundError) as exc:
            logger.warning("Mensaje rechazado -- trace_id=%s: %s", trace_id, exc)
            diagnosis = FailureDiagnosis(
                category=FailureCategory.CONFIGURATION, stage=FailureStage.CARGA_INSTANTANEA,
                code="configuration.snapshot_not_found", summary=str(exc), exception_type=type(exc).__name__,
            )
            raise _DiagnosedHTTPError(status.HTTP_404_NOT_FOUND, diagnosis, trace_id) from exc
        except Exception as exc:  # noqa: BLE001 - Ronda 93: la carga de la instantánea también se diagnostica
            diagnosis = diagnose_exception(exc, FailureStage.CARGA_INSTANTANEA)
            logger.error(
                "No se pudo cargar la instantánea -- proyecto=%s trace_id=%s categoria=%s etapa=%s codigo=%s\n%s",
                project_id, trace_id, diagnosis.category.value, diagnosis.stage.value, diagnosis.code,
                format_traceback(exc),
            )
            pinned = runtime_context.pinned_identity()
            version = pinned[1] if pinned else 0
            log_id = _guardar_fallo(project_id, version, request, trace_id, diagnosis)
            raise _DiagnosedHTTPError(
                status.HTTP_503_SERVICE_UNAVAILABLE, diagnosis, trace_id, log_id=log_id, snapshot_version=version,
            ) from exc

        handler = HandleIncomingMessage(
            loaded.conversational_service, log_repository, channeling_dispatcher=channeling_dispatcher,
            execution_base=loaded.execution_base,
        )
        # loaded.lock (auditoría Ronda 10, hallazgo A2): serializa el
        # manejo de mensajes contra ESTA instantánea -- QdrantLocalVectorStore
        # abre un QdrantClient(path=...) por operación, cuyo lock exclusivo
        # (flock) es por apertura de archivo, no por proceso; dos
        # solicitudes concurrentes del mismo proyecto/versión competían por
        # ese lock y la segunda fallaba con un 500. No afecta a otros
        # proyectos/versiones (cada uno tiene su propio lock).
        #
        # auto_dispatch_channeling=False (auditoría Ronda 46, hallazgo
        # #146, corregido en la Ronda 51): el lock de arriba solo existe
        # para proteger QdrantLocalVectorStore (ver docstring de
        # LoadedSnapshot.lock) -- entregar el evento de canalización a
        # un webhook externo no toca Qdrant en absoluto, pero antes de
        # esta corrección igual se ejecutaba (con sus reintentos y
        # espera, ver WebhookChannelingDispatcher) DENTRO del `with
        # loaded.lock`, bloqueando sin necesidad a cualquier otro
        # visitante de la MISMA instantánea mientras un webhook lento o
        # caído agotaba sus reintentos. `dispatch_channeling()` se
        # llama aparte, ya fuera del lock.
        try:
            with loaded.lock:
                handled = handler.execute(
                    project_id, loaded.snapshot.version, request.message, provided_variables=request.variables,
                    conversation_id=request.conversation_id, max_access_level=max_access_level,
                    auto_dispatch_channeling=False, trace_id=trace_id,
                )
        except MessageHandlingFailedError as exc:
            raise _DiagnosedHTTPError(
                status.HTTP_500_INTERNAL_SERVER_ERROR, exc.diagnosis, trace_id,
                log_id=exc.log_entry.id if exc.log_entry else None, snapshot_version=loaded.snapshot.version,
            ) from exc
        handler.dispatch_channeling(project_id, handled.log_entry, handled.trace)
        # Ronda 11: registro operativo del mensaje atendido -- a
        # propósito, NUNCA el texto del mensaje ni de la respuesta (eso
        # ya vive, estructurado, en runtime.db vía ConversationLogRepository,
        # con su propio ciclo de vida/retención -- ver pestaña Monitoreo);
        # este log es para diagnosticar el SERVICIO, no para duplicar la
        # bitácora de negocio.
        logger.info(
            "Mensaje atendido -- proyecto=%s version=%s accion=%s intencion=%s latencia_ms=%.1f "
            "log_id=%s conversacion_id=%s trace_id=%s",
            project_id, loaded.snapshot.version, handled.trace.action.value,
            handled.trace.matched_intent_name, handled.log_entry.latency_ms, handled.log_entry.id,
            handled.log_entry.conversation_id, trace_id,
        )
        # Ronda 104b (Etapa 0): los datos de ejecución siempre se guardan en
        # runtime.db, pero en la respuesta solo viajan para la credencial
        # operativa (o sin clave configurada, modo local de pruebas) -- nunca
        # para un token de widget, que llega desde navegadores públicos.
        operador = api_key is None or (x_api_key is not None and secrets.compare_digest(x_api_key, api_key))
        return MessageResponse.from_handled_message(handled, include_execution=operador)

    @app.post(
        "/projects/{project_id}/messages/{log_id}/feedback", response_model=RetrievalFeedbackResponse,
        dependencies=[Depends(_require_message_auth)],
    )
    def post_message_feedback(
        project_id: str, log_id: str, request: RetrievalFeedbackRequest,
    ) -> RetrievalFeedbackResponse:
        # Pista C.4a del ADR-003 (docs proyecto/
        # RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx):
        # capacidad opcional, documentada en CONTRATO_INTEGRACION.md --
        # el agente conversacional externo no está obligado a llamarla.
        # Reutiliza _require_message_auth (misma credencial que ya
        # protege POST /messages, ver nota de cierre de C.4a sobre por
        # qué) -- aquí no se necesita el max_access_level que devuelve,
        # así que va en `dependencies=[...]` (se descarta el valor),
        # nunca como parámetro con Annotated (ver el comentario extenso
        # junto a post_message sobre por qué eso rompería la
        # autenticación en este módulo).
        for item in request.entries:
            try:
                signal = FeedbackSignal(item.signal)
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"signal inválida: {item.signal!r}",
                ) from exc
            try:
                record_feedback.execute(
                    project_id, log_id, item.source_id, signal, FeedbackOrigin.AGENTE_EXTERNO,
                    chunk_id=item.chunk_id, notes=item.notes,
                )
            except ConversationLogEntryNotFoundError as exc:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return RetrievalFeedbackResponse(recorded=len(request.entries))

    @app.exception_handler(_DiagnosedHTTPError)
    def _on_diagnosed_error(_request, exc: _DiagnosedHTTPError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(Exception)
    def _on_unexpected_error(_request, exc: Exception) -> JSONResponse:
        # Ronda 93: cualquier otro error no previsto también responde con
        # categoría, etapa y trace_id (antes: 500 en texto plano).
        trace_id = _sanear_trace_id(_request.headers.get("X-Trace-Id"))
        diagnosis = diagnose_exception(exc)
        logger.error(
            "Error no esperado -- ruta=%s trace_id=%s categoria=%s etapa=%s codigo=%s\n%s",
            _request.url.path, trace_id, diagnosis.category.value, diagnosis.stage.value, diagnosis.code,
            format_traceback(exc),
        )
        return _DiagnosedHTTPError(status.HTTP_500_INTERNAL_SERVER_ERROR, diagnosis, trace_id).to_response()

    @app.exception_handler(ValueError)
    def _on_value_error(_request, exc: ValueError) -> JSONResponse:
        # SnapshotInstallationPaths.project_dir levanta ValueError si se
        # pidiera un project_id distinto del que sirve la instantánea
        # cargada -- no debería poder pasar por esta ruta (siempre se
        # pide con el mismo project_id de la URL), pero se traduce a un
        # 500 explícito en vez de dejar escapar un error no manejado.
        trace_id = _sanear_trace_id(_request.headers.get("X-Trace-Id"))
        diagnosis = diagnose_exception(exc)
        logger.error(
            "Error no esperado (ValueError) -- trace_id=%s categoria=%s codigo=%s\n%s",
            trace_id, diagnosis.category.value, diagnosis.code, format_traceback(exc),
        )
        return _DiagnosedHTTPError(status.HTTP_500_INTERNAL_SERVER_ERROR, diagnosis, trace_id).to_response()

    return app


def create_app_from_env() -> FastAPI:
    """Punto de entrada para `uvicorn interfaces.api.app:create_app_from_env
    --factory` -- lee y VALIDA la configuración de las variables de
    entorno (Ronda 92, ver interfaces/api/runtime_config.py) antes de
    construir nada: si algo falta o no coincide, el proceso no arranca y
    el error enumera todas las causas."""
    from app.configuration import default_base_dir

    config = load_runtime_config(os.environ, default_home=str(default_base_dir()))

    # Ronda 11: registro propio de este proceso ("ragstudio-api.log", no
    # "ragstudio.log", para no competir con la app de escritorio).
    configure_logging(
        InstallationPaths(config.installation_dir).logs_dir(), level=config.log_level, filename="ragstudio-api.log",
    )
    for aviso in config.warnings:
        logger.warning("Configuración del runtime: %s", aviso)

    channeling_dispatcher = (
        WebhookChannelingDispatcher(config.webhook_url, secret=config.webhook_secret)
        if config.webhook_url else None
    )
    logger.info("Arrancando runtime de RAG STUDIO -- %s", "; ".join(config.summary_lines()))

    pinned = config.pinned
    return create_app(
        config.installation_dir, embedding_profile=config.embedding_profile, api_key=config.api_key,
        runtime_db_path=config.runtime_db_path, allowed_origins=config.allowed_origins,
        channeling_dispatcher=channeling_dispatcher,
        pinned_snapshot_dir=pinned.directory if pinned else None,
        pinned_snapshot_version=pinned.version if pinned else None,
        pinned_project_id=pinned.project_id if pinned else None,
        rate_limit_per_minute=config.rate_limit_per_minute,
    )


app = create_app_from_env() if (
    os.environ.get("RAGSTUDIO_API_KEY") or any(os.environ.get(name) for name in LEGACY_API_KEY_VARS)
) else None
"""Solo se construye al importar el módulo si ya hay configuración de
entorno lista (p. ej. bajo `uvicorn interfaces.api.app:app` con
RAGSTUDIO_API_KEY ya definida) -- así `from interfaces.api.app import
create_app` sigue funcionando en pruebas sin necesitar ninguna
variable de entorno.

Auditoría Ronda 10, hallazgo B14: si falta RAGSTUDIO_API_KEY, `app`
queda en `None` EN SILENCIO -- `uvicorn interfaces.api.app:app` falla
entonces con un error de ASGI genérico ("TypeError: 'NoneType' object
is not callable"), no con el `RuntimeError` explícito que
`create_app_from_env` ya levanta para ese caso exacto (ese mensaje
nunca se llega a mostrar). Para que un despliegue real muestre siempre
el error explícito en vez de este síntoma críptico, arrancar con el
factory en vez de con este atributo de módulo (ver docstring del
módulo):

    uvicorn interfaces.api.app:create_app_from_env --factory
"""
