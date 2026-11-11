"""Bootstrap de la aplicación: ensambla domain + application +
infrastructure + workers en un único AppContext que usa la UI
(ADR-001, sección 3). No contiene reglas de negocio.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from application.conversational.service import ConversationalService
from application.diagnostics_facade import DiagnosticsFacade
from application.documents.service import DocumentService
from application.ingestion.service import IngestionService
from application.jobs_facade import BackgroundJobs
from application.metadata.service import MetadataService
from application.pipeline.service import PipelineService
from application.plugins.service import PluginService
from application.projects.service import ProjectService
from application.quality.service import QualityService
from application.rag.service import RagService
from application.release.service import ReleaseService
from application.runtime.service import RuntimeMonitoringService
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository,
    SqlAlchemyConversationalVariableRepository,
    SqlAlchemyGuardrailRuleRepository,
    SqlAlchemyIntentRepository,
)
from infrastructure.database.document_repositories import SqlAlchemySourceRepository
from infrastructure.database.ingestion_repositories import (
    SqlAlchemyChunkRepository,
    SqlAlchemyExtractionRepository,
    SqlAlchemyFragmentationPolicyRepository,
)
from infrastructure.database.metadata_repositories import (
    SqlAlchemyCatalogRepository,
    SqlAlchemyMetadataSchemaRepository,
    SqlAlchemySourceMetadataRepository,
)
from infrastructure.database.pipeline_repositories import SqlAlchemyPipelineRunRepository
from infrastructure.database.plugin_repositories import SqlAlchemyPluginRepository
from infrastructure.database.quality_repositories import (
    SqlAlchemyEvaluationRunRepository,
    SqlAlchemyTestCaseRepository,
)
from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository
from infrastructure.database.release_repositories import (
    SqlAlchemyProjectSnapshotRepository,
    SqlAlchemyReleaseRecordRepository,
)
from infrastructure.database.repositories import (
    ProjectAgentRerankingReader,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyProjectRepository,
)
from infrastructure.database.runtime_repositories import (
    SqlAlchemyConversationLogRepository,
    SqlAlchemyRetrievalFeedbackRepository,
    SqlAlchemyWidgetTokenRepository,
)
from infrastructure.embeddings.fastembed_image_provider import FastEmbedImageProvider
from infrastructure.embeddings.fastembed_provider import AVAILABLE_EMBEDDING_PROFILES, make_provider_for_profile
from infrastructure.extraction.ocr_engine import ocr_dependencies_available, TesseractOcrEngine
from infrastructure.extraction.text_extractors import (
    CompositeTextExtractor,
    CsvExtractor,
    DocxExtractor,
    HtmlExtractor,
    ImageTextExtractor,
    JsonExtractor,
    PdfTextExtractor,
    TxtExtractor,
    XlsxExtractor,
    XmlExtractor,
)
from infrastructure.filesystem.deployment_packager import FilesystemDeploymentPackager
from infrastructure.filesystem.diagnostics import FilesystemDiagnosticsExporter
from infrastructure.filesystem.import_batch_ledger import JsonlImportBatchLedger
from infrastructure.filesystem.import_lock import FileImportLock
from infrastructure.filesystem.packager import FilesystemProjectPackager
from infrastructure.filesystem.paths import InstallationPaths
from infrastructure.filesystem.project_snapshot_publisher import FilesystemProjectSnapshotPublisher
from infrastructure.filesystem.release_packager import FilesystemReleasePackager
from infrastructure.filesystem.source_file_store import FilesystemSourceFileStore
from application.knowledge_package.commands.export_knowledge_package import ExportKnowledgePackage
from infrastructure.exporters.nexom_knowledge_package import NexomKnowledgePackageExporter
from infrastructure.filesystem.source_original_hasher import FilesystemSourceOriginalHasher
from infrastructure.filesystem.backfill_report_store import JsonBackfillReportStore
from infrastructure.database.content_hash_writer import SqliteSourceContentHashWriter
from infrastructure.rerankers.fastembed_cross_encoder import FastEmbedReranker
from infrastructure.security.keyring_credential_store import KeyringCredentialStore
from infrastructure.tokenization.tiktoken_counter import TiktokenCounter
from infrastructure.vectorstores.qdrant_local_store import QdrantLocalVectorStore
from workers.jobs import ThreadJobRunner

from .configuration import AppSettings, load_settings
from .logging_setup import configure_logging, install_global_exception_hooks


@dataclass
class AppContext:
    settings: AppSettings
    paths: InstallationPaths
    project_service: ProjectService
    document_service: DocumentService
    metadata_service: MetadataService
    ingestion_service: IngestionService
    rag_service: RagService
    pipeline_service: PipelineService
    conversational_service: ConversationalService
    quality_service: QualityService
    monitoring_service: RuntimeMonitoringService
    release_service: ReleaseService
    plugin_service: PluginService
    jobs: BackgroundJobs
    diagnostics: DiagnosticsFacade
    logger: logging.Logger
    # RAG-INC-01b: exportador CORE del NEXOM Knowledge Package (solo caso de
    # uso; sin interfaz de usuario en este incremento).
    knowledge_package_export: Optional[ExportKnowledgePackage] = None


def bootstrap(
    base_dir: Optional[str | Path] = None, log_level: str = "INFO",
    embedding_profile: Optional[str] = None, max_concurrent_jobs: Optional[int] = None,
) -> AppContext:
    settings = load_settings(
        base_dir=base_dir, log_level=log_level, embedding_profile=embedding_profile,
        max_concurrent_jobs=max_concurrent_jobs,
    )
    paths = InstallationPaths(settings.base_dir)
    paths.ensure_installation_layout()

    logger = configure_logging(paths.logs_dir(), level=settings.log_level)
    # Ítem 5 de la segunda evaluación de madurez post-8-etapas (ver
    # bitácora): registra cualquier excepción no capturada (fuera de
    # los try/except explícitos de application/UI/ThreadJobRunner) en
    # este mismo log, en vez de perderse sin dejar rastro utilizable
    # para diagnosticar un problema real del usuario.
    install_global_exception_hooks(logger)
    logger.info("Iniciando RAG STUDIO. base_dir=%s", settings.base_dir)

    repository = SqlAlchemyProjectRepository(paths)
    configuration_repository = SqlAlchemyConfigurationRepository(paths)
    packager = FilesystemProjectPackager(paths)

    # source_repository se construye antes de ProjectService (y no
    # después, como antes) porque delete_project() (Ronda 3, punto 13)
    # necesita poder consultar si un proyecto ya tiene fuentes
    # registradas antes de permitir su borrado real -- mismo motivo por
    # el que extraction_repository se adelanta más abajo para
    # DocumentService.
    source_repository = SqlAlchemySourceRepository(paths)
    project_service = ProjectService(
        repository, configuration_repository, packager, source_repository,
        # RAG-INC-01a: bloqueo entre procesos de la importación (INC01-R9).
        import_lock=FileImportLock(paths.base_dir),
    )
    # extraction_repository se construye aquí (antes que IngestionService)
    # porque DocumentService también la necesita: para saber si ya se
    # puede bloquear la edición de location/source_type de una fuente
    # (ver UpdateSourceDetails/SourceStructuralFieldsLockedError) hace
    # falta poder consultar si esa fuente ya tiene una extracción
    # guardada, sin importar que ese dato "viva" en el contexto Ingesta.
    extraction_repository = SqlAlchemyExtractionRepository(paths)
    # source_file_store copia el archivo original a sources/original/
    # del proyecto al registrar una fuente (o al corregir su ubicación
    # mientras siga sin bloquear) -- así la extracción deja de depender
    # de que la ruta externa original siga existiendo (ver README,
    # "Limitaciones conocidas" y bitácora).
    source_file_store = FilesystemSourceFileStore(paths)
    document_service = DocumentService(
        source_repository, extraction_repository, file_store=source_file_store,
        batch_ledger=JsonlImportBatchLedger(paths),
        # RAG-INC-01 (INC01-R1, opción B): relleno explícito de content_hash.
        original_hasher=FilesystemSourceOriginalHasher(paths),
        content_hash_writer=SqliteSourceContentHashWriter(paths),
        backfill_report_store=JsonBackfillReportStore(paths),
    )

    schema_repository = SqlAlchemyMetadataSchemaRepository(paths)
    catalog_repository = SqlAlchemyCatalogRepository(paths)
    source_metadata_repository = SqlAlchemySourceMetadataRepository(paths)
    metadata_service = MetadataService(
        schema_repository, catalog_repository, source_metadata_repository, source_repository
    )

    # OCR (Módulo 4) es una dependencia opcional (extra "ocr"): si las
    # librerías (pytesseract, Pillow, PyMuPDF) no están instaladas, se
    # sigue construyendo PdfTextExtractor sin ocr_engine -- el mismo
    # comportamiento de siempre (advertencia por página, sin extraer
    # nada de páginas escaneadas), sin exigirle esta dependencia a
    # quien no la necesita.
    ocr_engine = TesseractOcrEngine() if ocr_dependencies_available() else None
    if ocr_engine is None:
        logger.info(
            "OCR no disponible (falta pytesseract/Pillow/PyMuPDF) -- PDF escaneado "
            "seguirá sin producir texto. Instala el extra 'ocr' para habilitarlo."
        )
    # El mismo motor OCR (o su ausencia) se comparte entre
    # PdfTextExtractor (respaldo para páginas escaneadas) e
    # ImageTextExtractor (Módulo 5, imagen_escaneada como fuente
    # independiente): sin él, ambos siguen produciendo solo una
    # advertencia clara, igual que antes de Módulo 4.
    text_extractor = CompositeTextExtractor([
        TxtExtractor(), DocxExtractor(),
        PdfTextExtractor(ocr_engine=ocr_engine), ImageTextExtractor(ocr_engine=ocr_engine),
        XlsxExtractor(), CsvExtractor(), HtmlExtractor(), JsonExtractor(), XmlExtractor(),
    ])
    chunk_repository = SqlAlchemyChunkRepository(paths)
    fragmentation_policy_repository = SqlAlchemyFragmentationPolicyRepository(paths)
    # token_counter (ítem 7 de la evaluación de madurez post-8-etapas):
    # tokenizador BPE real (tiktoken) para decidir tamaños de fragmento
    # y para Chunk.token_count, en vez de la aproximación por conteo de
    # palabras -- capacidad opcional (igual patrón que ocr_engine): si
    # la codificación no se ha podido descargar todavía (sin internet
    # en el primer uso), FragmentSource cae de vuelta a la aproximación
    # de siempre para esa corrida, sin romper la fragmentación.
    token_counter = TiktokenCounter()
    ingestion_service = IngestionService(
        source_repository, text_extractor, extraction_repository, fragmentation_policy_repository,
        chunk_repository, schema_repository, source_metadata_repository, token_counter=token_counter,
    )

    embedding_provider = make_provider_for_profile(settings.embedding_profile, cache_dir=paths.models_dir())
    vector_store = QdrantLocalVectorStore(paths)
    index_info_repository = SqlAlchemyIndexInfoRepository(paths)
    # embedding_provider_factory habilita el comparador de modelos A vs B
    # (RagService.compare_profiles): necesita poder construir un
    # EmbeddingProvider para CUALQUIER perfil bajo demanda, no solo el
    # que ya está activo como embedding_provider -- por eso se pasa la
    # función completa, no una instancia ya resuelta.
    rag_service = RagService(
        chunk_repository, embedding_provider, vector_store, index_info_repository,
        embedding_provider_factory=lambda profile: make_provider_for_profile(profile, cache_dir=paths.models_dir()),
        available_embedding_profiles=list(AVAILABLE_EMBEDDING_PROFILES),
        # source_repository habilita el filtro "solo fuentes vigentes y
        # validadas" en la búsqueda semántica (Módulo 4: control de
        # documentos excluidos) -- ver domain.documents.entities.Source.
        # is_usable_for_responses y SemanticSearch.
        source_repository=source_repository,
        # reranker habilita "Reranking real (cross-encoder)" en el
        # Laboratorio RAG (ADR-003, Pista A.2) -- carga perezosa, igual
        # que embedding_provider: no descarga el modelo de Hugging Face
        # hasta la primera búsqueda híbrida que de verdad lo pida.
        reranker=FastEmbedReranker(cache_dir=paths.models_dir()),
        # image_embedding_provider habilita index_image_source()/
        # search_images() (Fase 3 de multimodalidad nativa, RAG 3) --
        # misma carga perezosa que el resto: no descarga ningún modelo
        # de Hugging Face hasta la primera fuente IMAGEN_NATIVA que de
        # verdad se indexe o busque. Siempre se construye (no depende
        # de ningún extra opcional, a diferencia de ocr_engine) porque
        # fastembed ya es una dependencia declarada del núcleo.
        image_embedding_provider=FastEmbedImageProvider(cache_dir=paths.models_dir()),
    )

    # Etapa 3, "pipeline reproducible": corre extraer+fragmentar+indexar
    # sobre todas las fuentes del proyecto de una sola vez, reutilizando
    # ingestion_service/rag_service ya construidos (no reimplementa
    # nada de Ingesta/RAG).
    pipeline_run_repository = SqlAlchemyPipelineRunRepository(paths)
    pipeline_service = PipelineService(source_repository, ingestion_service, rag_service, pipeline_run_repository)

    # Etapa 5, "Diseño conversacional": intenciones, variables
    # conversacionales, guardrails y esquemas de canalización, más el
    # simulador que los conecta con rag_service (búsqueda) y
    # source_metadata_repository (filtros derivados de variables --
    # "Dato conversacional → Campo de metadatos → Filtro de
    # recuperación"). Reutiliza rag_service/source_metadata_repository
    # ya construidos, no duplica nada de Ingesta/RAG.
    intent_repository = SqlAlchemyIntentRepository(paths)
    conversational_variable_repository = SqlAlchemyConversationalVariableRepository(paths)
    guardrail_rule_repository = SqlAlchemyGuardrailRuleRepository(paths)
    channeling_scheme_repository = SqlAlchemyChannelingSchemeRepository(paths)
    conversational_service = ConversationalService(
        intent_repository, conversational_variable_repository, guardrail_rule_repository,
        channeling_scheme_repository, source_metadata_repository, rag_service,
        source_repository=source_repository, schema_repository=schema_repository,
        catalog_repository=catalog_repository,
        # Ronda 102 (C4): ajuste "Reranking en el agente" del proyecto.
        agent_reranking=ProjectAgentRerankingReader(paths),
    )

    # Etapa 8, "Complementos": registro global (application.db, no
    # project.db -- un complemento no pertenece a un proyecto) de
    # plantillas, nuevos proveedores, importadores y evaluadores
    # personalizados, con un cargador dinámico real
    # (domain/plugins/loader.py) que valida el contrato de cada tipo.
    # Se construye ANTES que quality_service (aunque es "Etapa 8" y
    # quality_service es "Etapa 6"): RunEvaluation ahora invoca los
    # complementos EVALUADOR activos durante una corrida real (ver
    # bitácora), así que necesita plugin_repository ya disponible.
    # credential_store: ítem 2 de la segunda evaluación de madurez
    # post-8-etapas (ver bitácora). KeyringCredentialStore es una
    # capacidad opcional -- si el almacén seguro del sistema operativo
    # no está disponible (sin sesión gráfica/Secret Service, p. ej. un
    # servidor headless), PluginService cae de vuelta a guardar
    # config en texto plano, igual que antes de este ítem (ver
    # register_plugin.externalize_secrets).
    plugin_repository = SqlAlchemyPluginRepository(paths)
    credential_store = KeyringCredentialStore()
    plugin_service = PluginService(plugin_repository, credential_store=credential_store)

    # Etapa 6, "Calidad": banco de pruebas + corridas de evaluación
    # (semáforos, regresión, bloqueos) sobre conversational_service --
    # cada caso de prueba es, en el fondo, una llamada a
    # ConversationalService.simulate(), sin reimplementar el motor
    # conversacional. plugin_repository conecta los complementos
    # EVALUADOR de Etapa 8 a una corrida real (ver bitácora).
    test_case_repository = SqlAlchemyTestCaseRepository(paths)
    evaluation_run_repository = SqlAlchemyEvaluationRunRepository(paths)
    quality_service = QualityService(
        test_case_repository, evaluation_run_repository, conversational_service,
        plugin_repository=plugin_repository,
    )

    # ADR-002, Fase 5 ("lazo de mejora continua"): pestaña de
    # Monitoreo -- lee la misma bitácora de conversaciones reales
    # (`runtime.db`) que ya escribe `interfaces/api/` (Fase 2), sin
    # necesitar que ese proceso esté corriendo (es un SQLite normal en
    # modo WAL). Reutiliza `test_case_repository` para poder promover
    # cualquier conversación real a un caso de prueba de Calidad --
    # mismo repositorio, sin duplicar wiring.
    conversation_log_repository = SqlAlchemyConversationLogRepository(paths.runtime_db_path())
    # feedback_repository (Pista C.4a del ADR-003): mismo runtime.db,
    # tabla nueva -- ver infrastructure/database/runtime_repositories.py.
    # Habilita el canal operador ("Marcar relevante"/"Marcar
    # irrelevante") del panel de Monitoreo.
    feedback_repository = SqlAlchemyRetrievalFeedbackRepository(paths.runtime_db_path())
    # widget_token_repository: comparte el mismo runtime.db que
    # conversation_log_repository (mismo archivo, distintas tablas -- ver
    # infrastructure/database/runtime_repositories.py). Antes de la Ronda
    # 10 ningún componente de la app de escritorio necesitaba emitir
    # tokens de widget -- eso solo pasaba vía interfaces/api/. Ahora lo
    # necesita el paquete de entrega al cliente (export_deployment_package,
    # más abajo), que emite uno nuevo por cada exportación -- y, desde la
    # Ronda 56, también RuntimeMonitoringService.evaluate_reopening_criteria()
    # (por eso se construye ANTES de monitoring_service, no después: antes
    # de esta ronda no le hacía falta a nadie más que a release_service,
    # que se construye más abajo).
    widget_token_repository = SqlAlchemyWidgetTokenRepository(paths.runtime_db_path())
    monitoring_service = RuntimeMonitoringService(
        conversation_log_repository, test_case_repository, feedback_repository=feedback_repository,
        # project_repository/widget_token_repository (Ronda 56): habilitan
        # evaluate_reopening_criteria() -- `repository` (ProjectRepository
        # global) ya se construyó más arriba, se reutiliza sin duplicar
        # wiring, mismo criterio que el resto de esta función.
        project_repository=repository, widget_token_repository=widget_token_repository,
    )

    # Etapa 7, "Documentación y liberación": compuertas de avance sobre
    # los seis contextos anteriores (metadatos, fragmentación, pipeline,
    # índice, diseño conversacional, calidad) + compilación de los 8
    # entregables formales -- no reimplementa ninguna verificación, solo
    # consulta lo que cada fachada ya expone.
    release_record_repository = SqlAlchemyReleaseRecordRepository(paths)
    # snapshot_repository/snapshot_publisher (ADR-002, Fase 1): publican
    # una copia de solo lectura del proyecto -- project.db + índice
    # Qdrant -- separada de projects/<project_id>, para un futuro
    # runtime de producción. reutiliza `repository` (ProjectRepository
    # global, ya construido arriba) solo para validar que el proyecto
    # existe antes de publicar, igual criterio que ExportProject.
    project_snapshot_repository = SqlAlchemyProjectSnapshotRepository(paths)
    project_snapshot_publisher = FilesystemProjectSnapshotPublisher(paths)
    release_service = ReleaseService(
        release_record_repository, metadata_service, ingestion_service, pipeline_service, rag_service,
        conversational_service, quality_service,
        # release_packager (ítem 6 de la evaluación de madurez
        # post-8-etapas): genera un paquete .zip real con los 8
        # entregables formales de una liberación ya evaluada, en vez
        # de dejarlos solo como JSON en línea en el registro.
        release_packager=FilesystemReleasePackager(),
        project_repository=repository,
        snapshot_repository=project_snapshot_repository,
        snapshot_publisher=project_snapshot_publisher,
        # deployment_packager (Ronda 10): paquete de entrega al cliente --
        # reutiliza widget_token_repository ya construido para Monitoreo
        # (mismo runtime.db) para emitir un token nuevo por cada
        # exportación, sin duplicar wiring.
        widget_token_repository=widget_token_repository,
        deployment_packager=FilesystemDeploymentPackager(),
    )

    # max_concurrent_jobs: ítem 4 de la segunda evaluación de madurez
    # post-8-etapas (ver bitácora) -- None (default) es sin límite,
    # igual que siempre; configurable vía RAGSTUDIO_MAX_CONCURRENT_JOBS
    # o el parámetro explícito a load_settings/bootstrap/start.
    jobs = BackgroundJobs(ThreadJobRunner(max_concurrent_jobs=settings.max_concurrent_jobs))

    # diagnostics: ítem 5 de la segunda evaluación de madurez
    # post-8-etapas (ver bitácora) -- exporta un .zip con info.json
    # (versiones, sistema operativo) + los archivos de logs/, para
    # adjuntar a soporte sin que el usuario tenga que ir a buscar la
    # carpeta de instalación a mano.
    diagnostics = DiagnosticsFacade(FilesystemDiagnosticsExporter(paths))

    logger.info("Bootstrap completo.")
    return AppContext(
        settings=settings,
        paths=paths,
        project_service=project_service,
        document_service=document_service,
        metadata_service=metadata_service,
        ingestion_service=ingestion_service,
        rag_service=rag_service,
        pipeline_service=pipeline_service,
        conversational_service=conversational_service,
        quality_service=quality_service,
        monitoring_service=monitoring_service,
        release_service=release_service,
        plugin_service=plugin_service,
        jobs=jobs,
        diagnostics=diagnostics,
        logger=logger,
        knowledge_package_export=ExportKnowledgePackage(
            project_snapshot_repository, NexomKnowledgePackageExporter(),
        ),
    )
