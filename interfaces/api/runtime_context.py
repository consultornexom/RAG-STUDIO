"""Construye y cachea, por proyecto, los servicios de aplicación
necesarios para atender mensajes reales (ADR-002, Fase 2) -- siempre
contra la instantánea publicada más reciente (`ProjectSnapshot`, Fase
1), nunca contra `projects/<project_id>` en edición.

Cachea instancias por versión para no reabrir el proveedor de
embeddings ni reconstruir repositorios en cada solicitud (ADR-002,
sección 5, riesgos "arranque en frío" y "conexión por llamada") -- el
proveedor de embeddings se calienta una vez, al construirse, y queda
en memoria para las siguientes solicitudes del mismo proceso.

Ronda 12/13 (ver Validacion_observaciones_RAG_STUDIO.md): la caché
desaloja las versiones SUPERADAS de un mismo proyecto en cuanto se
carga una nueva (ver `_get_or_build`) -- sin esto, un proceso de larga
duración al que se le publicaran instantáneas nuevas del mismo
proyecto una y otra vez acumulaba en memoria, sin límite, cada versión
anterior (incluido su proveedor de embeddings), aunque `get_latest`
nunca vuelve a pedirlas. No desaloja entre proyectos distintos -- cada
proyecto activo sigue con su propia instancia en memoria mientras se le
consulte."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from application.conversational.service import ConversationalService
from application.rag.service import RagService
from domain.rag.exceptions import RerankingRequiredUnavailableError
from domain.rag.ports import EmbeddingProvider, ImageEmbeddingProvider, Reranker
from domain.release.entities import ProjectSnapshot
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository,
    SqlAlchemyConversationalVariableRepository,
    SqlAlchemyGuardrailRuleRepository,
    SqlAlchemyIntentRepository,
)
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import SqlAlchemyChunkRepository
from infrastructure.database.metadata_repositories import (
    SqlAlchemyCatalogRepository, SqlAlchemyMetadataSchemaRepository, SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.database.release_repositories import SqlAlchemyProjectSnapshotRepository
from infrastructure.build_info import current_code_identity
from infrastructure.database.repositories import ProjectAgentRerankingReader
from infrastructure.embeddings.caching_provider import CachingEmbeddingProvider
from infrastructure.embeddings.fastembed_image_provider import FastEmbedImageProvider
from infrastructure.embeddings.fastembed_provider import AVAILABLE_EMBEDDING_PROFILES, make_provider_for_profile
from infrastructure.filesystem.paths import InstallationPaths, SnapshotInstallationPaths
from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker
from infrastructure.filesystem.snapshot_identity import (
    SnapshotIdentityError, content_fingerprint, read_snapshot_identity,
)
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore

EmbeddingProviderFactory = Callable[[str, Path], EmbeddingProvider]
# ImageEmbeddingProviderFactory (Ronda 68, cierre del vacío 2 de la
# Ronda 66): mismo patrón de "costura de prueba" que
# EmbeddingProviderFactory arriba -- sin él, ninguna prueba de
# integración podría ejercer de verdad el canal image_results del
# runtime HTTP sin depender de red (FastEmbedImageProvider descarga un
# modelo CLIP real de Hugging Face en su primer uso).
ImageEmbeddingProviderFactory = Callable[[Path], ImageEmbeddingProvider]
# Ronda 105b (P1): el Runtime solo construye un reranker para los proyectos
# con «Reranking en el agente: Activado». Inyectable para pruebas sin red.
RerankerFactory = Callable[[Path], Reranker]


def _default_embedding_provider_factory(profile: str, cache_dir: Path) -> EmbeddingProvider:
    return make_provider_for_profile(profile, cache_dir=cache_dir)


def _default_image_embedding_provider_factory(cache_dir: Path) -> ImageEmbeddingProvider:
    return FastEmbedImageProvider(cache_dir=cache_dir)


def _default_reranker_factory(cache_dir: Path) -> Reranker:
    return FastEmbedReranker(cache_dir=cache_dir)


class SnapshotNotFoundError(Exception):
    """El proyecto todavía no tiene ninguna instantánea publicada
    (ADR-002, Fase 1) -- nada que el runtime pueda servir todavía."""

    def __init__(self, project_id: str, served_project_id: Optional[str] = None):
        if served_project_id is not None:
            mensaje = (
                f"Este runtime sirve una instantánea fija del proyecto {served_project_id!r}; "
                f"no atiende al proyecto {project_id!r}. Revisa el id en la URL."
            )
        else:
            mensaje = (
                f"El proyecto {project_id!r} no tiene ninguna instantánea publicada. "
                "Publica una desde la pestaña de Liberación en RAG STUDIO antes de usar este runtime."
            )
        super().__init__(mensaje)
        self.project_id = project_id


@dataclass
class LoadedSnapshot:
    snapshot: ProjectSnapshot
    conversational_service: ConversationalService
    lock: threading.Lock
    """Auditoría Ronda 10, hallazgo A2: `QdrantLocalVectorStore` abre un
    `QdrantClient(path=...)` por operación y lo cierra en `finally` --
    el lock exclusivo que toma (`flock`) es por *open file
    description*, no por proceso: dos solicitudes concurrentes contra
    la MISMA instantánea (el mismo hilo del threadpool de FastAPI
    atendiendo dos visitantes a la vez) chocan entre sí con un
    RuntimeError sin capturar. Serializar el manejo de mensajes por
    instantánea (ver `post_message`, interfaces/api/app.py) evita la
    colisión sin serializar entre proyectos/versiones distintos, que
    no comparten directorio de índice -- `RuntimeContext._build` crea
    un lock nuevo por cada instantánea que carga."""
    execution_base: Optional[dict] = None
    """Ronda 104b (Etapa 0): parte fija de los datos de ejecución de esta
    instantánea en este proceso -- código, instantánea (huella declarada y
    calculada al cargar), índice y disponibilidad del reranker. Ver
    application/runtime/execution_info.py."""


class RuntimeContext:
    """Punto único de acceso del proceso API a las instantáneas
    publicadas de una instalación de RAG STUDIO.

    `installation_dir` es la instalación de escritorio de la que se
    leen las instantáneas (`snapshots/<project_id>/v<n>/` y el
    registro de versiones en cada `project.db`) -- de solo lectura
    para este proceso, salvo la propia tabla de registro de
    instantáneas, que ya tolera lectores/escritores concurrentes
    (SQLite en modo WAL, ver infrastructure/database/engine.py).

    `embedding_profile` es el perfil que este proceso usa para
    calcular embeddings de consulta -- un solo perfil por proceso
    (ADR-002, sección 5): si distintos proyectos publicados necesitan
    perfiles distintos, hoy exige procesos de runtime separados.

    `embedding_provider_factory` es inyectable (mismo criterio que
    `RagService.embedding_provider_factory`) para que las pruebas
    puedan sustituir el modelo real de fastembed -- que descarga
    varios cientos de MB en su primer uso -- por un doble en memoria,
    sin tocar el resto del cableado.

    `image_embedding_provider_factory` (Ronda 68): mismo criterio que
    `embedding_provider_factory`, pero para el canal de imágenes (Fase
    3 de multimodalidad nativa, RAG 3) -- inyectable para que las
    pruebas sustituyan FastEmbedImageProvider (modelo CLIP real, que
    también descarga de Hugging Face) sin tocar el resto del cableado."""

    def __init__(
        self, installation_dir: str | Path, embedding_profile: str = "simetrico",
        embedding_provider_factory: Optional[EmbeddingProviderFactory] = None,
        image_embedding_provider_factory: Optional[ImageEmbeddingProviderFactory] = None,
        pinned_snapshot_dir: Optional[str | Path] = None, pinned_snapshot_version: Optional[int] = None,
        pinned_project_id: Optional[str] = None,
        reranker_factory: Optional[RerankerFactory] = None,
    ):
        self._installation_paths = InstallationPaths(installation_dir)
        self._reranker_factory = reranker_factory or _default_reranker_factory
        self._embedding_profile = embedding_profile
        self._embedding_provider_factory = embedding_provider_factory or _default_embedding_provider_factory
        self._image_embedding_provider_factory = (
            image_embedding_provider_factory or _default_image_embedding_provider_factory
        )
        self._lock = threading.Lock()
        self._loaded: dict[str, LoadedSnapshot] = {}
        # pinned_snapshot_dir (auditoría Ronda 10, hallazgos A3/B1):
        # cuando se configura, este proceso sirve SIEMPRE esa instantánea
        # exacta -- sin consultar el registro de ProjectSnapshotRepository
        # (que vive en projects/<project_id>/project.db, el que la app de
        # escritorio sigue editando, y que un paquete de entrega al
        # cliente no incluye) y sin depender de que ese registro apunte a
        # una ruta absoluta válida en ESTA máquina. Resuelve de un tiro
        # los dos problemas reales que encontró la auditoría al intentar
        # desplegar un paquete de entrega en una instalación nueva, y de
        # paso cumple la promesa de "instantánea congelada" que ya hacía
        # el informe de entrega (antes, sin fijar versión, `get_latest`
        # empezaba a servir cualquier instantánea nueva que se publicara
        # en la instalación de origen, sin que el operador lo pidiera).
        self._pinned_snapshot_dir = Path(pinned_snapshot_dir) if pinned_snapshot_dir is not None else None
        # Ronda 92: sin versión por defecto. Si quien construye el contexto
        # no la indica, se deriva de la propia instantánea
        # (snapshot_identity.json / manifest.json del paquete) y, si no se
        # puede, se falla aquí -- antes se asumía 1 en silencio.
        if self._pinned_snapshot_dir is not None and (pinned_snapshot_version is None or pinned_project_id is None):
            from .runtime_config import RuntimeConfigurationError, resolve_pinned_snapshot

            problems: list[str] = []
            declarada = None if pinned_snapshot_version is None else str(pinned_snapshot_version)
            resuelta = resolve_pinned_snapshot(self._pinned_snapshot_dir, declarada, problems)
            if resuelta is None:
                # Con versión explícita se tolera una carpeta que todavía no
                # es servible (get_latest responderá 404 como antes), pero
                # nunca una versión que contradiga la identidad declarada.
                if pinned_snapshot_version is None or any("no coincide" in p for p in problems):
                    raise RuntimeConfigurationError(problems)
            else:
                pinned_snapshot_version = resuelta.version
                pinned_project_id = pinned_project_id or resuelta.project_id
        self._pinned_snapshot_version = pinned_snapshot_version
        self._pinned_project_id = pinned_project_id

    def loaded_project_ids(self) -> list[str]:
        """Claves "project_id:version" de las instantáneas ya
        calentadas en este proceso -- solo para el endpoint de salud;
        no expone ningún dato de negocio."""
        with self._lock:
            return sorted(self._loaded.keys())

    def pinned_identity(self) -> Optional[tuple[Optional[str], int]]:
        """(proyecto, versión) de la instantánea fija, o None en modo
        registro -- para /health."""
        if self._pinned_snapshot_dir is None or self._pinned_snapshot_version is None:
            return None
        return self._pinned_project_id, self._pinned_snapshot_version

    def get_latest(self, project_id: str) -> LoadedSnapshot:
        if self._pinned_snapshot_dir is not None:
            # Ronda 92 (auditoría): antes la instantánea fija respondía a
            # CUALQUIER project_id de la URL, presentando el contenido de un
            # proyecto bajo el id de otro. Ahora solo atiende al suyo.
            if self._pinned_project_id is not None and project_id != self._pinned_project_id:
                raise SnapshotNotFoundError(project_id, served_project_id=self._pinned_project_id)
            assert self._pinned_snapshot_version is not None
            snapshot = ProjectSnapshot(
                project_id=project_id, version=self._pinned_snapshot_version,
                snapshot_dir=str(self._pinned_snapshot_dir),
            )
        else:
            snapshot_repository = SqlAlchemyProjectSnapshotRepository(self._installation_paths)
            latest = snapshot_repository.get_latest(project_id)
            if latest is None:
                raise SnapshotNotFoundError(project_id)
            snapshot = latest
        # Auditoría Ronda 10, hallazgo A4: sin esta verificación,
        # `SnapshotInstallationPaths.project_dir` + `ensure_project_db`
        # (invocado por el primer repositorio que se use, dentro de
        # `_build`) CREAN en silencio un project.db vacío ya migrado si
        # el directorio no existe -- el runtime respondería como un
        # proyecto sin nada configurado (siempre "abstenerse"), sin
        # ningún error, en vez de fallar de forma explícita. Falla aquí,
        # antes de construir nada.
        if not (Path(snapshot.snapshot_dir) / "project.db").exists():
            raise SnapshotNotFoundError(project_id)
        return self._get_or_build(project_id, snapshot)

    def _get_or_build(self, project_id: str, snapshot: ProjectSnapshot) -> LoadedSnapshot:
        key = f"{project_id}:{snapshot.version}"
        with self._lock:
            cached = self._loaded.get(key)
            if cached is not None:
                return cached
            loaded = self._build(project_id, snapshot)
            self._loaded[key] = loaded
            # Desalojo de versiones superadas (deuda documentada desde la
            # auditoría de la Ronda 10, cerrada en la Ronda 12): sin esto,
            # `self._loaded` crecía sin límite en un proceso de larga
            # duración al que se le publicaran instantáneas nuevas del
            # mismo proyecto una y otra vez -- cada versión anterior se
            # quedaba en memoria (incluido su proveedor de embeddings, que
            # puede pesar varios cientos de MB) sin que nada volviera a
            # pedirla nunca: `get_latest` SIEMPRE resuelve la versión más
            # reciente del registro (o la instantánea fijada, que nunca
            # cambia de versión -- ver `pinned_snapshot_dir`), así que una
            # versión reemplazada es inalcanzable desde el instante en que
            # se publica la siguiente. Desalojar solo las versiones DEL
            # MISMO proyecto (nunca las de otros proyectos, que sí se
            # siguen consultando en paralelo) y solo después de construir
            # la nueva con éxito -- si `_build` fallara, la versión
            # anterior (todavía servible) permanece intacta en la caché.
            stale_keys = [
                other_key for other_key in self._loaded
                if other_key != key and other_key.rsplit(":", 1)[0] == project_id
            ]
            for stale_key in stale_keys:
                del self._loaded[stale_key]
            return loaded

    def _build(self, project_id: str, snapshot: ProjectSnapshot) -> LoadedSnapshot:
        # Ronda 104b (Etapa 0): la huella se calcula ANTES de abrir nada
        # (abrir project.db puede aplicarle migraciones y cambiarla).
        snapshot_block = describe_snapshot(snapshot)
        paths = SnapshotInstallationPaths(project_id, snapshot.snapshot_dir, self._installation_paths.base_dir)

        source_repository = SqlAlchemySourceRepository(paths)
        source_metadata_repository = SqlAlchemySourceMetadataRepository(paths)
        chunk_repository = SqlAlchemyChunkRepository(paths)
        # CachingEmbeddingProvider (Ronda 19, ver caching_provider.py):
        # envuelve el proveedor real solo para el lado consulta -- cada
        # instantánea (project_id:version) tiene su propio caché, que se
        # descarta junto con ella cuando `_get_or_build` desaloja
        # versiones superadas (ver más abajo), nunca sirve un resultado
        # calculado contra una versión anterior del proyecto.
        embedding_provider = CachingEmbeddingProvider(
            self._embedding_provider_factory(self._embedding_profile, paths.models_dir())
        )
        vector_store = QdrantLocalVectorStore(paths)
        index_info_repository = SqlAlchemyIndexInfoRepository(paths)
        # Ronda 105b (P1, alternativa B estricta, decisión de NEXOM): solo un
        # proyecto con «Reranking en el agente: Activado» necesita el modelo.
        # Se construye y se CARGA aquí, al cargar la instantánea; si no carga,
        # la instantánea no se sirve (error explícito, sin degradar). Los
        # demás proyectos no construyen reranker: mismo comportamiento y mismos
        # requisitos de siempre.
        agent_reranking = ProjectAgentRerankingReader(paths)
        reranker: Optional[Reranker] = None
        if agent_reranking(project_id) is True:
            reranker = self._reranker_factory(paths.models_dir())
            try:
                reranker.ensure_ready()
            except Exception as exc:  # noqa: BLE001 - se reexpresa como error de configuración explícito
                raise RerankingRequiredUnavailableError(
                    f"El proyecto {project_id!r} (instantánea v{snapshot.version}) tiene «Reranking en el agente: "
                    f"Activado», pero este servidor no pudo cargar el modelo de reranking "
                    f"{getattr(reranker, 'model_name', '?')!r}. Aprovisione el modelo en la carpeta de modelos del "
                    "Runtime o cambie el ajuste del proyecto y publique una versión nueva. "
                    f"Detalle: {type(exc).__name__}: {exc}"
                ) from exc
        rag_service = RagService(
            chunk_repository, embedding_provider, vector_store, index_info_repository,
            embedding_provider_factory=lambda profile: self._embedding_provider_factory(
                profile, paths.models_dir(),
            ),
            available_embedding_profiles=list(AVAILABLE_EMBEDDING_PROFILES),
            source_repository=source_repository,
            # image_embedding_provider (cierre del vacío 2 de la Ronda 66,
            # Fase 3 de multimodalidad nativa): sin esto,
            # RagService.has_image_search sería siempre False en este
            # proceso -- SimulateConversation nunca poblaría
            # SimulationTrace.image_results (ni, por lo tanto,
            # MessageResponse.image_results) sin importar cuántas
            # imágenes tenga indexadas el proyecto. Misma carga perezosa
            # que app/bootstrap.py ya usa para el runtime de escritorio
            # (FastEmbedImageProvider, el factory por defecto, no
            # descarga ningún modelo hasta el primer embed_images/
            # embed_query_text real -- y SemanticSearchImages, además,
            # nunca llega a llamarlo si el proyecto no tiene ninguna
            # imagen indexada, ver el atajo de VectorStore.count() en
            # ese módulo) -- construirlo aquí siempre, sin condicionarlo
            # a nada, no tiene costo de arranque en frío adicional.
            image_embedding_provider=self._image_embedding_provider_factory(paths.models_dir()),
            reranker=reranker,
        )
        intent_repository = SqlAlchemyIntentRepository(paths)
        conversational_variable_repository = SqlAlchemyConversationalVariableRepository(paths)
        guardrail_rule_repository = SqlAlchemyGuardrailRuleRepository(paths)
        channeling_scheme_repository = SqlAlchemyChannelingSchemeRepository(paths)
        conversational_service = ConversationalService(
            intent_repository, conversational_variable_repository, guardrail_rule_repository,
            channeling_scheme_repository, source_metadata_repository, rag_service,
            # Ronda 89: mismo motor que el Simulador de escritorio.
            source_repository=source_repository,
            schema_repository=SqlAlchemyMetadataSchemaRepository(paths),
            catalog_repository=SqlAlchemyCatalogRepository(paths),
            # Ronda 102 (C4): el ajuste "Reranking en el agente" se lee de la
            # instantánea servida (mismo project.db que el resto).
            agent_reranking=agent_reranking,
        )
        # Calentar el proveedor de embeddings ahora (al construir,
        # nunca en la primera solicitud real) -- ADR-002, sección 5,
        # riesgo de arranque en frío: sin esto, la primera conversación
        # de cada versión publicada pagaría el costo de cargar el
        # modelo a RAM.
        rag_service.embed_query("calentamiento del proveedor de embeddings")

        info = rag_service.get_index_info(project_id)
        execution_base = {
            "code": current_code_identity().to_dict(),
            "snapshot": snapshot_block,
            "index": {
                "embedding_provider": info.embedding_provider if info else None,
                "embedding_model": info.embedding_model if info else None,
                "dimensions": info.dimensions if info else None,
                "points_count": info.points_count if info else None,
                "updated_at": info.updated_at.isoformat() if info else None,
                "query_embedding_profile": self._embedding_profile,
                "query_embedding_model": getattr(embedding_provider, "model_name", None),
            },
            "reranking": {
                "model_available": rag_service.reranker_loaded,
                "available_model": rag_service.reranker_model_name,
            },
        }
        return LoadedSnapshot(
            snapshot=snapshot, conversational_service=conversational_service, lock=threading.Lock(),
            execution_base=execution_base,
        )

    def loaded_execution_bases(self) -> list[dict]:
        """Ronda 104b (Etapa 0): datos fijos de las instantáneas cargadas,
        para /health/details."""
        with self._lock:
            return [loaded.execution_base for loaded in self._loaded.values() if loaded.execution_base]

    def pinned_snapshot_description(self) -> Optional[dict]:
        """Ronda 104b (Etapa 0): identidad declarada de la instantánea fija
        (sin cargarla ni calcular su huella), para /health/details."""
        if self._pinned_snapshot_dir is None:
            return None
        try:
            identidad = read_snapshot_identity(self._pinned_snapshot_dir)
        except (SnapshotIdentityError, OSError):
            identidad = None
        return {
            "project_id": self._pinned_project_id, "version": self._pinned_snapshot_version,
            "identity_file": identidad is not None,
            "declared_fingerprint": identidad.content_fingerprint if identidad else None,
            "published_at": identidad.published_at if identidad else None,
        }


def describe_snapshot(snapshot: ProjectSnapshot) -> dict:
    """Ronda 104b (Etapa 0): identidad de una instantánea para los datos de
    ejecución: huella declarada al publicar (snapshot_identity.json) y huella
    calculada al cargarla en este proceso. Si no coinciden, la instantánea
    cambió desde su publicación (p. ej. la abrió antes un proceso que le
    aplicó migraciones). Nunca incluye la ruta del servidor."""
    identidad = None
    error = None
    try:
        identidad = read_snapshot_identity(snapshot.snapshot_dir)
    except (SnapshotIdentityError, OSError) as exc:
        error = type(exc).__name__
    try:
        al_cargar: Optional[str] = content_fingerprint(snapshot.snapshot_dir)
    except OSError:
        al_cargar = None
    declarada = identidad.content_fingerprint if identidad else None
    return {
        "project_id": snapshot.project_id, "version": snapshot.version,
        "identity_file": identidad is not None, "identity_error": error,
        "declared_fingerprint": declarada,
        "published_at": identidad.published_at if identidad else None,
        "fingerprint_at_load": al_cargar,
        "fingerprint_matches": (declarada == al_cargar) if declarada and al_cargar else None,
    }

