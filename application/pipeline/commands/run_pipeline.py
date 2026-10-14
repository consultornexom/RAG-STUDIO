"""Caso de uso: correr el pipeline completo (extraer + fragmentar +
indexar) sobre todas las fuentes de un proyecto -- "EjecutarPipeline"
en la vista de capas de ADR-001 (Etapa 3, "pipeline reproducible").

Depende de IngestionService y RagService (otros servicios de
application, no de infrastructure directamente) para no reimplementar
extracción/fragmentación/indexación -- ADR-001, sección 4, solo prohíbe
que application dependa de infrastructure concreta, ui o SDKs de
proveedores; componer servicios ya existentes de la misma capa es el
mismo patrón que ya usa RagService (que a su vez compone varias
queries/comandos internos).
"""
from __future__ import annotations

import logging

import hashlib
from typing import Callable, Optional

from domain.documents.entities import SourceType
from domain.documents.ports import SourceRepository
from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus
from domain.pipeline.ports import PipelineRunRepository

logger = logging.getLogger(__name__)


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _hash_file(location: str) -> Optional[str]:
    """Hash del contenido real del archivo (no de `Source.content_hash`,
    que es un campo opcional que la UI nunca completa hoy -- ver
    bitácora). Es la señal de incrementalidad: si el archivo no cambió
    desde la última corrida exitosa de esa fuente, se omite sin volver
    a extraer/fragmentar/indexar. None si el archivo no se pudo leer
    (fuerza reprocesar -- el error real de lectura saldrá al intentar
    extraer, capturado igual que cualquier otro error de esta fuente)."""
    try:
        digest = hashlib.sha256()
        with open(location, "rb") as file:
            for block in iter(lambda: file.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


class RunPipeline:
    def __init__(
        self,
        source_repository: SourceRepository,
        ingestion_service,  # application.ingestion.service.IngestionService
        rag_service,  # application.rag.service.RagService
        pipeline_run_repository: PipelineRunRepository,
    ):
        self._sources = source_repository
        self._ingestion = ingestion_service
        self._rag = rag_service
        self._runs = pipeline_run_repository

    def execute(
        self, project_id: str, document_type_code: str = "default",
        schema_id: Optional[str] = None, is_cancelled: Callable[[], bool] = lambda: False,
    ) -> PipelineRun:
        """Corre extraer+fragmentar+indexar sobre todas las fuentes del
        proyecto. Siempre devuelve (y guarda) una PipelineRun -- incluso
        si se cancela a medio camino o alguna fuente falla: "corridas
        con errores/evidencias" es justo el punto (Compuerta 3), no una
        excepción que tumbe el lote completo.
        """
        run = PipelineRun(project_id=project_id, document_type_code=document_type_code)
        sources = self._sources.list_for_project(project_id)

        for source in sources:
            if is_cancelled():
                run.status = PipelineRunStatus.CANCELADO
                break
            item = self._process_source(project_id, source, document_type_code, schema_id, is_cancelled)
            run.items.append(item)
            if item.status == PipelineItemStatus.CANCELADO:
                run.status = PipelineRunStatus.CANCELADO
                break
        else:
            run.status = (
                PipelineRunStatus.COMPLETO_CON_ERRORES if run.has_critical_errors
                else PipelineRunStatus.COMPLETO
            )

        run.finished_at = _utcnow()
        self._runs.save(run)
        return run

    def _process_source(
        self, project_id: str, source, document_type_code: str,
        schema_id: Optional[str], is_cancelled: Callable[[], bool],
    ) -> PipelineRunItem:
        started_at = _utcnow()
        content_hash = _hash_file(source.location)

        last_item = self._runs.get_last_successful_item(project_id, source.id)
        if content_hash is not None and last_item is not None and last_item.content_hash == content_hash:
            # Incrementalidad/reanudación: el archivo no cambió desde la
            # última vez que esta fuente se proceso con éxito -- no
            # hace falta volver a extraer/fragmentar/indexar.
            return PipelineRunItem(
                source_id=source.id, source_title=source.title, status=PipelineItemStatus.OMITIDO,
                content_hash=content_hash, steps_completed=list(last_item.steps_completed),
                chunks_indexed=last_item.chunks_indexed, started_at=started_at, finished_at=_utcnow(),
            )

        steps_completed: list[str] = []
        warnings: list[str] = []
        try:
            record = self._ingestion.extract_source_text(project_id, source.id, is_cancelled=is_cancelled)
            if record is None:
                return PipelineRunItem(
                    source_id=source.id, source_title=source.title, status=PipelineItemStatus.CANCELADO,
                    content_hash=content_hash, started_at=started_at, finished_at=_utcnow(),
                )
            warnings.extend(record.warnings)
            steps_completed.append("extraccion")

            chunks = self._ingestion.fragment_source(
                project_id, source.id, schema_id=schema_id, document_type_code=document_type_code,
                is_cancelled=is_cancelled,
            )
            if chunks is None:
                return PipelineRunItem(
                    source_id=source.id, source_title=source.title, status=PipelineItemStatus.CANCELADO,
                    content_hash=content_hash, steps_completed=steps_completed, warnings=warnings,
                    started_at=started_at, finished_at=_utcnow(),
                )
            steps_completed.append("fragmentacion")

            # Fase 3/4 de multimodalidad nativa (RAG 3): una fuente
            # SourceType.IMAGEN_NATIVA se indexa con
            # RagService.index_image_source, no con index_source (el de
            # texto) -- este último no produciría ningún error visible,
            # simplemente indexaría 0 fragmentos en silencio, porque una
            # imagen nativa nunca pasa por FragmentSource (Ronda 65,
            # punto 221). Los pasos de extracción/fragmentación de
            # arriba siguen corriendo igual para una imagen (producen un
            # ExtractionRecord de texto vacío y cero Chunk, ver Ronda
            # 65/66) -- son inofensivos pero no aportan nada; no hace
            # falta suprimirlos para no complicar este método con una
            # rama completa aparte solo para imágenes.
            if source.source_type == SourceType.IMAGEN_NATIVA:
                n_indexed = self._rag.index_image_source(project_id, source.id)
            else:
                n_indexed = self._rag.index_source(project_id, source.id)
            steps_completed.append("indexacion")

            return PipelineRunItem(
                source_id=source.id, source_title=source.title, status=PipelineItemStatus.EXITOSO,
                content_hash=content_hash, steps_completed=steps_completed, chunks_indexed=n_indexed,
                warnings=warnings, started_at=started_at, finished_at=_utcnow(),
            )
        except Exception as exc:  # noqa: BLE001 -- fault-isolation intencional: un
            # error de una fuente no debe tumbar el resto del lote (a
            # diferencia del resto del código, donde se capturan
            # excepciones específicas). Aquí "capturar todo" es el
            # requisito: "corridas con errores/evidencias" (Compuerta 3).
            # Ronda 93 (auditoría): nunca un error vacío -- excepciones sin
            # mensaje dejaban la fila FALLIDO sin causa -- y con la traza en
            # el registro (antes no quedaba ninguna).
            etapa = steps_completed[-1] if steps_completed else "inicio"
            logger.exception("Pipeline: falló la fuente %s (%s) después de '%s'.", source.title, source.id, etapa)
            return PipelineRunItem(
                source_id=source.id, source_title=source.title, status=PipelineItemStatus.FALLIDO,
                content_hash=content_hash, steps_completed=steps_completed, warnings=warnings,
                error=f"{type(exc).__name__}: {str(exc).strip() or '(sin mensaje)'} (último paso completado: {etapa})",
                started_at=started_at, finished_at=_utcnow(),
            )
