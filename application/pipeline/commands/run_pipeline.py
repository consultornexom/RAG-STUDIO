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

Ronda 98 (hallazgo real de NEXOM, AGENTE UDL - LOTE01_Bachillerato: 5
fuentes de 3 tipos documentales con 3 políticas distintas):
- Política por fuente: cada fuente se fragmenta con la política de SU
  `document_type_code` (la "default" del proyecto solo si su tipo no
  tiene una propia). Antes, la pestaña Pipeline enviaba UN tipo y se
  aplicaba esa misma política a todas las fuentes. `document_type_code`
  explícito sigue aceptándose para forzar una sola política (uso
  excepcional, queda marcado como "forzada" en el reporte).
- Incrementalidad por configuración: una fuente se omite solo si NO
  cambió nada de lo que determina sus fragmentos e índice: el archivo
  (content_hash), la política aplicable (policy_hash), los metadatos que
  heredan los fragmentos (metadata_hash) y los fragmentos guardados
  (chunks_digest, por si se re-fragmentó a mano), y si su último intento
  de procesamiento terminó con éxito. La causa de cada decisión queda en
  PipelineRunItem.reason.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from domain.documents.entities import SourceType
from domain.documents.ports import SourceRepository
from domain.pipeline.entities import (
    PER_SOURCE_DOCUMENT_TYPE,
    PipelineItemStatus,
    PipelineRun,
    PipelineRunItem,
    PipelineRunStatus,
)
from domain.pipeline.ports import PipelineRunRepository

logger = logging.getLogger(__name__)


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _hash_file(location: Optional[str]) -> Optional[str]:
    """Hash del contenido real del archivo (no de `Source.content_hash`,
    que es un campo opcional que la UI nunca completa hoy -- ver
    bitácora). Es la señal de incrementalidad: si el archivo no cambió
    desde la última corrida exitosa de esa fuente, se omite sin volver
    a extraer/fragmentar/indexar. None si el archivo no se pudo leer
    (fuerza reprocesar -- el error real de lectura saldrá al intentar
    extraer, capturado igual que cualquier otro error de esta fuente)."""
    if not location:
        return None
    try:
        digest = hashlib.sha256()
        with open(location, "rb") as file:
            for block in iter(lambda: file.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


@dataclass(frozen=True)
class _Config:
    """Lo que determina los fragmentos e índice de una fuente."""

    document_type_code: str
    policy_document_type_code: Optional[str]
    policy_origin: str
    policy_strategy: str
    policy_description: str
    policy_hash: str
    metadata_hash: str
    chunks_digest: str
    policy_hash_sin_version: str = ""
    """Huella con la regla de la Ronda 98 (sin versión de fragmentador):
    permite explicar que el único cambio es la versión del fragmentador."""


def _sha256_json(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _chunks_digest(chunks) -> str:
    """Huella de los fragmentos guardados: lo que se indexa y se exporta
    (texto, tipo, sección, páginas, metadatos heredados), en orden. Los
    ids no entran: cambian en cada fragmentación aunque el resultado sea el mismo."""
    return _sha256_json([
        [c.chunk_index, getattr(c.chunk_type, "value", c.chunk_type), c.section_title, c.page_start, c.page_end,
         c.text, sorted((c.inherited_metadata or {}).items())]
        # Ronda 100: la ruta de encabezados entra solo si existe, para que
        # los fragmentos sin ruta conserven exactamente la huella de antes.
        + ([[h.level, h.title] for h in c.section_path] if getattr(c, "section_path", None) else [])
        for c in sorted(chunks, key=lambda c: c.chunk_index)
    ])


FRAGMENTER_VERSIONS = {"por_encabezado": "ruta-de-encabezados-v1"}
"""Ronda 100: versión del fragmentador por estrategia. Si cambia lo que una
estrategia produce (por_encabezado ahora guarda Chunk.section_path), su
versión entra en la huella de política y el pipeline reprocesa SOLO las
fuentes con esa estrategia, sin reconstruir el resto del índice."""


def _read_path(source) -> Optional[str]:
    """Ronda 98: el archivo que de verdad se extrae -- la copia local en
    sources/original/ si existe (ver ExtractSourceText), si no la ruta
    externa. Antes el hash se calculaba siempre sobre `location`: un
    cambio en el archivo externo marcaba "cambió" aunque la extracción
    siguiera leyendo la copia (reproceso sin efecto), y en un proyecto
    llevado a otro equipo, donde `location` no existe, la fuente se
    reprocesaba en TODAS las corridas (hash None)."""
    return getattr(source, "original_copy_path", None) or source.location


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
        self, project_id: str, document_type_code: Optional[str] = None,
        schema_id: Optional[str] = None, is_cancelled: Callable[[], bool] = lambda: False,
    ) -> PipelineRun:
        """Corre extraer+fragmentar+indexar sobre todas las fuentes del
        proyecto. Siempre devuelve (y guarda) una PipelineRun -- incluso
        si se cancela a medio camino o alguna fuente falla: "corridas
        con errores/evidencias" es justo el punto (Compuerta 3), no una
        excepción que tumbe el lote completo.

        Ronda 98: `document_type_code=None` (por defecto) aplica a cada
        fuente la política de su propio tipo documental. Un valor explícito
        fuerza esa política para todas las fuentes.
        """
        forzado = (document_type_code or "").strip() or None
        run = PipelineRun(project_id=project_id, document_type_code=forzado or PER_SOURCE_DOCUMENT_TYPE)
        sources = self._sources.list_for_project(project_id)

        for source in sources:
            if is_cancelled():
                run.status = PipelineRunStatus.CANCELADO
                break
            item = self._process_source(project_id, source, forzado, schema_id, is_cancelled)
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

    def plan(self, project_id: str, schema_id: Optional[str] = None) -> list[dict]:
        """Ronda 98: vista previa SIN efectos (no extrae, no fragmenta, no
        indexa ni guarda nada) de lo que haría execute() con cada fuente:
        tipo documental, política aplicable y si se omitiría o reprocesaría
        (con la causa). Sirve para revisar las políticas antes de correr el
        pipeline sobre un lote real."""
        filas = []
        for source in self._sources.list_for_project(project_id):
            fila: dict = {"source_id": source.id, "source_title": source.title}
            try:
                config = self._config_for(project_id, source, None, schema_id)
                motivos = self._skip_or_reasons(
                    _hash_file(_read_path(source)), config,
                    self._runs.get_last_processed_item(project_id, source.id),
                    self._runs.get_last_successful_item(project_id, source.id),
                )
                fila.update({
                    "document_type_code": config.document_type_code, "policy": config.policy_description,
                    "policy_origin": config.policy_origin, "accion": "reprocesar" if motivos else "omitir",
                    "motivo": " ".join(motivos) or "Sin cambios.",
                })
            except Exception as exc:  # noqa: BLE001 - una fuente con problema no impide ver las demás
                fila.update({"accion": "error", "motivo": f"{type(exc).__name__}: {exc}"})
            filas.append(fila)
        return filas

    def _config_for(self, project_id: str, source, forzado: Optional[str], schema_id: Optional[str]) -> _Config:
        tipo_fuente = (getattr(source, "document_type_code", None) or "default").strip() or "default"
        tipo_politica = forzado or tipo_fuente
        policy, origen = self._ingestion.resolve_fragmentation_policy(project_id, tipo_politica)
        if forzado:
            origen = "forzada"
        estrategia = getattr(policy.strategy, "value", policy.strategy)
        parametros = {
            "document_type_code": policy.document_type_code if origen != "interna" else None,
            "strategy": estrategia, "target_tokens": policy.target_tokens,
            "overlap_tokens": policy.overlap_tokens, "min_tokens": policy.min_tokens,
        }
        version = FRAGMENTER_VERSIONS.get(estrategia)
        hash_sin_version = _sha256_json(parametros)
        if version:
            parametros = {**parametros, "fragmentador": version}
        heredados = self._ingestion.resolve_inherited_metadata(project_id, schema_id, source.id)
        nombre = parametros["document_type_code"] or "interna de RAG Studio"
        return _Config(
            document_type_code=tipo_fuente,
            policy_document_type_code=parametros["document_type_code"],
            policy_origin=origen,
            policy_strategy=estrategia,
            policy_description=(
                f"{nombre} ({estrategia}, {policy.target_tokens}/{policy.overlap_tokens}/{policy.min_tokens})"
            ),
            policy_hash=_sha256_json(parametros), policy_hash_sin_version=hash_sin_version,
            metadata_hash=_sha256_json(sorted(heredados.items())),
            chunks_digest=_chunks_digest(self._ingestion.list_chunks(project_id, source.id)),
        )

    @staticmethod
    def _skip_or_reasons(content_hash: Optional[str], config: _Config, last_processed, last_success) -> list[str]:
        """Lista vacía = se puede omitir. Si no, las causas de reprocesar."""
        if content_hash is None:
            return ["No se pudo leer el archivo de la fuente (se intenta procesar para mostrar el error real)."]
        if last_success is None:
            return ["Fuente nueva o nunca procesada con éxito."]
        if last_processed is not None and last_processed.status != PipelineItemStatus.EXITOSO:
            return [
                f"El último intento de procesar esta fuente terminó como {last_processed.status.value}: "
                "los fragmentos o el índice podrían no estar completos."
            ]
        motivos: list[str] = []
        if last_success.content_hash != content_hash:
            motivos.append("El archivo cambió.")
        if last_success.policy_hash is None:
            motivos.append(
                "La corrida anterior no registró la política ni los metadatos aplicados (versión previa de "
                "RAG Studio); se reprocesa una vez con la política de su tipo documental."
            )
            return motivos
        if last_success.policy_hash != config.policy_hash and last_success.policy_hash == config.policy_hash_sin_version:
            motivos.append(
                f"Nueva versión del fragmentador {config.policy_strategy} "
                f"({FRAGMENTER_VERSIONS.get(config.policy_strategy)}): ahora guarda la ruta de encabezados de cada "
                "fragmento; misma política."
            )
        elif last_success.policy_hash != config.policy_hash:
            antes = last_success.policy_document_type_code or "interna de RAG Studio"
            motivos.append(
                f"Cambió la política de fragmentación aplicable (antes: {antes} / {last_success.policy_strategy}; "
                f"ahora: {config.policy_description})."
            )
        if last_success.metadata_hash != config.metadata_hash:
            motivos.append("Cambiaron los metadatos que heredan los fragmentos.")
        if last_success.chunks_digest is not None and last_success.chunks_digest != config.chunks_digest:
            motivos.append("Los fragmentos guardados cambiaron fuera del pipeline (por ejemplo, se re-fragmentó a mano).")
        return motivos

    def _process_source(
        self, project_id: str, source, forzado: Optional[str],
        schema_id: Optional[str], is_cancelled: Callable[[], bool],
    ) -> PipelineRunItem:
        started_at = _utcnow()
        content_hash = _hash_file(_read_path(source))
        steps_completed: list[str] = []
        warnings: list[str] = []
        traza: dict = {"document_type_code": getattr(source, "document_type_code", None)}
        try:
            config = self._config_for(project_id, source, forzado, schema_id)
            traza = {
                "document_type_code": config.document_type_code,
                "policy_document_type_code": config.policy_document_type_code,
                "policy_origin": config.policy_origin, "policy_strategy": config.policy_strategy,
                "policy_hash": config.policy_hash, "metadata_hash": config.metadata_hash,
            }
            last_processed = self._runs.get_last_processed_item(project_id, source.id)
            last_success = self._runs.get_last_successful_item(project_id, source.id)
            motivos = self._skip_or_reasons(content_hash, config, last_processed, last_success)
            if not motivos and last_success is not None:
                # Incrementalidad/reanudación: ni el archivo ni la
                # configuración de procesamiento cambiaron desde la última
                # vez que esta fuente se procesó con éxito.
                return PipelineRunItem(
                    source_id=source.id, source_title=source.title, status=PipelineItemStatus.OMITIDO,
                    content_hash=content_hash, steps_completed=list(last_success.steps_completed),
                    chunks_indexed=last_success.chunks_indexed, started_at=started_at, finished_at=_utcnow(),
                    chunks_digest=config.chunks_digest,
                    reason=f"Sin cambios: mismo archivo, misma política ({config.policy_description}) y mismos "
                           "metadatos heredados.",
                    **traza,
                )
            traza["reason"] = " ".join(motivos)

            record = self._ingestion.extract_source_text(project_id, source.id, is_cancelled=is_cancelled)
            if record is None:
                return PipelineRunItem(
                    source_id=source.id, source_title=source.title, status=PipelineItemStatus.CANCELADO,
                    content_hash=content_hash, started_at=started_at, finished_at=_utcnow(), **traza,
                )
            warnings.extend(record.warnings)
            steps_completed.append("extraccion")

            chunks = self._ingestion.fragment_source(
                project_id, source.id, schema_id=schema_id,
                document_type_code=forzado or config.document_type_code, is_cancelled=is_cancelled,
            )
            if chunks is None:
                return PipelineRunItem(
                    source_id=source.id, source_title=source.title, status=PipelineItemStatus.CANCELADO,
                    content_hash=content_hash, steps_completed=steps_completed, warnings=warnings,
                    started_at=started_at, finished_at=_utcnow(), **traza,
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
                chunks_digest=_chunks_digest(self._ingestion.list_chunks(project_id, source.id)), **traza,
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
                started_at=started_at, finished_at=_utcnow(), **traza,
            )
