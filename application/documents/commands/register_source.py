"""Caso de uso: registrar una fuente (RAG STUDIO.odt, Módulo 2)."""
from __future__ import annotations

import logging
from typing import Optional

from domain.documents.entities import (
    NON_FILE_SOURCE_TYPES, AccessLevel, Source, SourceType, SourceValidationStatus,
)
from domain.documents.exceptions import DuplicateSourceError
from domain.documents.ports import SourceFileStore, SourceRepository

logger = logging.getLogger(__name__)


class RegisterSource:
    def __init__(self, repository: SourceRepository, file_store: Optional[SourceFileStore] = None):
        self._repository = repository
        self._file_store = file_store

    def find_by_content_hash(self, project_id: str, content_hash: Optional[str]) -> Optional[Source]:
        """Fuente ya registrada con ese contenido (Ronda 92: para enlazar
        una fila de lote reimportada con la fuente que ya la representa)."""
        if not content_hash:
            return None
        return self._repository.get_by_content_hash(project_id, content_hash)

    def execute(
        self,
        project_id: str,
        title: str,
        source_type: SourceType,
        location: str = "",
        owner_area: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.INTERNO,
        language: str = "es",
        content_hash: Optional[str] = None,
        valid_from=None,
        valid_to=None,
        source_authority: Optional[int] = None,
        supersedes_source_id: Optional[str] = None,
        document_type_code: str = "default",
    ) -> Source:
        if content_hash is not None:
            existing = self._repository.get_by_content_hash(project_id, content_hash)
            if existing is not None and existing.id != supersedes_source_id:
                raise DuplicateSourceError(content_hash)

        # RAG-INC-01a (migración 0021): una sucesora COPIA el lineage_id de la
        # fuente que supersede; sin supersesión válida, la fuente es raíz y
        # conserva el UUID4 nuevo por defecto (misma regla que el relleno de
        # 0021 para referencias rotas).
        lineage_kwargs: dict = {}
        if supersedes_source_id:
            predecesora = self._repository.get(project_id, supersedes_source_id)
            if predecesora is not None:
                lineage_kwargs["lineage_id"] = predecesora.lineage_id

        source = Source(
            project_id=project_id, title=title, source_type=source_type, location=location,
            owner_area=owner_area, access_level=access_level, language=language,
            content_hash=content_hash, valid_from=valid_from, valid_to=valid_to,
            source_authority=source_authority, supersedes_source_id=supersedes_source_id,
            document_type_code=document_type_code, **lineage_kwargs,
        )
        self._repository.save(source)
        source = self._try_copy_original(source)

        if supersedes_source_id:
            old = self._repository.get(project_id, supersedes_source_id)
            if old is None:
                # Auditoría profunda (ronda posterior a la 76, ver
                # bitácora): `supersedes_source_id` no resolvió a
                # ninguna fuente real (id mal escrito, de otro
                # proyecto, o borrada entre que se eligió y que se
                # confirmó el registro) -- antes se ignoraba en
                # silencio, sin ninguna advertencia, a diferencia de
                # _try_copy_original (que sí deja rastro en el log
                # técnico de sus propios fallos). El registro de la
                # fuente nueva ya se confirmó arriba, así que esto
                # nunca debe tumbarlo -- solo se advierte, mismo
                # criterio que _try_copy_original.
                logger.warning(
                    "La fuente nueva '%s' (id=%s) del proyecto '%s' declara "
                    "supersedes_source_id=%s, pero no existe ninguna fuente con "
                    "ese id en este proyecto -- la referencia queda guardada tal "
                    "cual (posible error de captura), y ninguna fuente anterior "
                    "se transiciona a SUSTITUIDO.",
                    source.title, source.id, project_id, supersedes_source_id,
                )
            elif old.validation_status == SourceValidationStatus.VALIDADO:
                self._repository.save(old.transition_validation_to(SourceValidationStatus.SUSTITUIDO))
            # Si la fuente anterior no estaba VALIDADO, la máquina de estados
            # no permite saltar directo a SUSTITUIDO; queda como limitación
            # documentada (ver README) en vez de forzar una transición.

        return source

    def _try_copy_original(self, source: Source) -> Source:
        """Copia `location` a sources/original/ del proyecto, si hay
        `file_store` configurado, la fuente es de un tipo con archivo
        real y `location` no está vacía. Cualquier fallo al copiar
        (ruta no legible en este momento, sin permisos...) nunca tumba
        el registro de la fuente -- la extracción simplemente sigue
        leyendo de `location` directamente, igual que antes de que
        existiera esta capacidad (ver ExtractSourceText.execute) -- pero
        sí queda una advertencia en el log técnico, para poder saber
        después por qué esa fuente terminó sin copia de respaldo."""
        if self._file_store is None or source.source_type in NON_FILE_SOURCE_TYPES:
            return source
        if not source.location.strip():
            return source
        try:
            copy_path = self._file_store.store_original(source.project_id, source.id, source.location)
        except Exception as exc:  # noqa: BLE001 - ver docstring: nunca debe tumbar el registro
            logger.warning(
                "No se pudo copiar el archivo original de la fuente '%s' (id=%s, "
                "ubicacion=%s) a sources/original/ del proyecto '%s'; el registro "
                "de la fuente continua sin copia de respaldo (%s).",
                source.title, source.id, source.location, source.project_id, exc,
            )
            return source
        updated = source.model_copy(update={"original_copy_path": copy_path})
        self._repository.save(updated)
        return updated
