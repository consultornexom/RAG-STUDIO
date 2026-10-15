"""Caso de uso: rellenar `content_hash` de fuentes heredadas (RAG-INC-01,
precondición técnica de 01b; decisión NEXOM sobre INC01-R1, opción B,
mecanismo "comando/servicio explícito"; migración 0022 descartada).

Flujo:
1. Lee las fuentes del proyecto.
2. Para cada fuente basada en archivo con `content_hash` NULL, calcula el
   SHA-256 de `<proyecto>/sources/original/<source_id>.<ext>` (nunca de
   `location`). Un fallo de lectura de una fuente no detiene a las demás.
3. Clasifica (domain.documents.content_hash_backfill.clasificar), incluida la
   regla de duplicados por (lineage_id, hash).
4. Escribe en UNA transacción solo donde el hash sigue NULL
   (SourceContentHashWriter). Si la escritura falla, no queda nada escrito.
5. Guarda el informe JSON en `<proyecto>/reports/` (también si la escritura
   se revirtió) y lo devuelve.

Es idempotente: una segunda ejecución sobre un proyecto completo no escribe
nada y reporta `ya_tenía`. No modifica instantáneas publicadas: después del
relleno hay que publicar una instantánea nueva antes de exportar un NKP.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from domain.documents.content_hash_backfill import (
    BackfillStatus,
    ContentHashBackfillReport,
    ESTADOS_QUE_ESCRIBEN,
    clasificar,
    necesita_hash,
)
from domain.documents.exceptions import OriginalCopyMissingError, OriginalCopyUnreadableError
from domain.documents.ports import (
    BackfillReportStore,
    SourceContentHashWriter,
    SourceOriginalHasher,
    SourceRepository,
)

logger = logging.getLogger(__name__)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class BackfillSourceContentHashes:
    def __init__(
        self, repository: SourceRepository, hasher: SourceOriginalHasher, writer: SourceContentHashWriter,
        report_store: Optional[BackfillReportStore] = None,
    ):
        self._repository = repository
        self._hasher = hasher
        self._writer = writer
        self._report_store = report_store

    def execute(self, project_id: str) -> ContentHashBackfillReport:
        informe = ContentHashBackfillReport(project_id=project_id, started_at=_ahora())
        fuentes = self._repository.list_for_project(project_id)
        informe.missing_before = sum(1 for s in fuentes if necesita_hash(s))

        calculados: dict[str, str] = {}
        fallos: dict[str, tuple[BackfillStatus, str]] = {}
        for fuente in fuentes:
            if not necesita_hash(fuente):
                continue
            try:
                calculados[fuente.id] = self._hasher.sha256_of_original(project_id, fuente)
            except OriginalCopyMissingError as exc:
                fallos[fuente.id] = (BackfillStatus.SIN_COPIA_ORIGINAL, str(exc))
            except OriginalCopyUnreadableError as exc:
                fallos[fuente.id] = (BackfillStatus.ILEGIBLE, str(exc))
            except OSError as exc:
                fallos[fuente.id] = (BackfillStatus.ILEGIBLE, f"{type(exc).__name__}: {exc}")

        informe.results = clasificar(fuentes, calculados, fallos)
        a_escribir: dict[str, str] = {}
        for r in informe.results:
            if r.status in ESTADOS_QUE_ESCRIBEN and r.content_hash:
                a_escribir[r.source_id] = r.content_hash

        try:
            escritos = self._writer.fill_missing(project_id, a_escribir)
        except Exception as exc:
            informe.write_outcome = "revertida"
            informe.error = f"{type(exc).__name__}: {exc}"
            informe.missing_after = informe.missing_before
            informe.finished_at = _ahora()
            self._guardar(informe)
            logger.warning("Relleno de content_hash revertido en el proyecto %s: %s", project_id, exc)
            raise

        # Fuentes que otro proceso completó entre el cálculo y la escritura.
        for r in informe.results:
            if r.status in ESTADOS_QUE_ESCRIBEN and r.source_id not in escritos:
                r.status = BackfillStatus.YA_TENIA
                r.detail = "otro proceso la completó durante el relleno; no se modificó."
        informe.write_outcome = "aplicada" if escritos else "sin_cambios"
        informe.missing_after = sum(1 for s in self._repository.list_for_project(project_id) if necesita_hash(s))
        informe.finished_at = _ahora()
        self._guardar(informe)
        logger.info(
            "Relleno de content_hash en %s: %d escritas, faltantes %d -> %d.",
            project_id, len(escritos), informe.missing_before, informe.missing_after,
        )
        return informe

    def _guardar(self, informe: ContentHashBackfillReport) -> None:
        if self._report_store is None:
            return
        try:
            informe.report_path = self._report_store.save(informe.project_id, informe.to_dict())
        except OSError as exc:  # el informe nunca debe deshacer una escritura ya confirmada
            logger.warning("No se pudo guardar el informe del relleno de content_hash: %s", exc)
