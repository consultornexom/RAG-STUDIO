"""Caso de uso: editar los campos capturados de una fuente ya
registrada (título, área propietaria, nivel de acceso, ubicación,
tipo, idioma).

Regla de negocio central (hallazgo real de validación visual, ver
README bitácora): título/área/nivel de acceso son descriptivos -- nada
se construye a partir de ellos, se pueden editar siempre. Ubicación y
tipo son estructurales -- extracción, fragmentos e índice vectorial se
construyen a partir de ellos -- así que solo se pueden editar mientras
la fuente todavía no tenga una extracción guardada; una vez que la
tiene, cambiarlos en silencio dejaría esos datos derivados apuntando a
un contenido que ya no es el real. Por eso este comando depende del
ExtractionRepository del contexto Ingesta, no solo del SourceRepository
de Documentos -- mismo patrón de dependencia cruzada entre contextos
de application ya usado en FragmentSource (que depende de
MetadataSchemaRepository/SourceMetadataRepository del contexto
Metadatos).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from domain.documents.entities import NON_FILE_SOURCE_TYPES, AccessLevel, Source, SourceType
from domain.documents.exceptions import SourceNotFoundError, SourceStructuralFieldsLockedError
from domain.documents.ports import SourceFileStore, SourceRepository
from domain.ingestion.ports import ExtractionRepository


class UpdateSourceDetails:
    def __init__(
        self, repository: SourceRepository, extraction_repository: ExtractionRepository,
        file_store: Optional[SourceFileStore] = None,
    ):
        self._repository = repository
        self._extraction_repository = extraction_repository
        self._file_store = file_store

    def execute(
        self,
        project_id: str,
        source_id: str,
        title: str,
        owner_area: Optional[str],
        access_level: AccessLevel,
        location: str,
        source_type: SourceType,
        valid_from: Optional[date] = None,
        valid_to: Optional[date] = None,
        source_authority: Optional[int] = None,
        document_type_code: str = "default",
        language: str = "es",
    ) -> Source:
        existing = self._repository.get(project_id, source_id)
        if existing is None:
            raise SourceNotFoundError(source_id)

        structural_change = location != existing.location or SourceType(source_type) != existing.source_type
        if structural_change:
            has_extraction = self._extraction_repository.get(project_id, source_id) is not None
            if has_extraction:
                raise SourceStructuralFieldsLockedError(source_id)

        updated = existing.with_updated_details(
            title=title, owner_area=owner_area, access_level=access_level,
            location=location, source_type=source_type,
            valid_from=valid_from, valid_to=valid_to, source_authority=source_authority,
            document_type_code=document_type_code, language=language,
        )
        if structural_change:
            # location/source_type solo pueden llegar aquí cuando
            # structural_change es True Y todavía no hay extracción
            # (ver arriba) -- la copia anterior en sources/original/
            # (si existía) ya no corresponde al `location` nuevo, así
            # que se limpia y se reintenta con el valor vigente, igual
            # criterio que RegisterSource._try_copy_original.
            updated = updated.model_copy(update={"original_copy_path": None})
            updated = self._try_copy_original(updated)
        self._repository.save(updated)
        return updated

    def _try_copy_original(self, source: Source) -> Source:
        if self._file_store is None or source.source_type in NON_FILE_SOURCE_TYPES:
            return source
        if not source.location.strip():
            return source
        try:
            copy_path = self._file_store.store_original(source.project_id, source.id, source.location)
        except Exception:  # noqa: BLE001 - ver RegisterSource._try_copy_original
            return source
        return source.model_copy(update={"original_copy_path": copy_path})
