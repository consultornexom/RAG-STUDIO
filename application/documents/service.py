"""Fachada de application para el contexto Documentos."""
from __future__ import annotations

from datetime import date
from typing import Optional

from domain.documents.entities import Source
from domain.documents.import_batch import ImportBatchRecord
from domain.documents.ports import ImportBatchLedger, SourceFileStore, SourceRepository
from domain.ingestion.ports import ExtractionRepository

from .commands.bulk_set_document_type_code import BulkSetDocumentTypeCode, BulkSetDocumentTypeCodeResult
from .commands.register_source import RegisterSource
from .commands.register_sources_from_folder import ImportSourcesFromFolderResult, RegisterSourcesFromFolder
from .commands.update_source_details import UpdateSourceDetails
from .commands.update_validation_status import UpdateSourceValidationStatus
from .lineage_export import format_source_lineage_as_csv
from .queries.get_source import GetSource
from .queries.get_source_lineage import GetSourceLineage
from .queries.list_sources import ListSources


class DocumentService:
    def __init__(
        self, repository: SourceRepository, extraction_repository: ExtractionRepository,
        file_store: Optional[SourceFileStore] = None, batch_ledger: Optional[ImportBatchLedger] = None,
    ):
        self._register = RegisterSource(repository, file_store=file_store)
        self._import_from_folder = RegisterSourcesFromFolder(self._register, batch_ledger=batch_ledger)
        self._batch_ledger = batch_ledger
        self._update_status = UpdateSourceValidationStatus(repository)
        self._update_details = UpdateSourceDetails(repository, extraction_repository, file_store=file_store)
        self._bulk_set_document_type_code = BulkSetDocumentTypeCode(repository)
        self._get = GetSource(repository)
        self._list = ListSources(repository)
        self._get_lineage = GetSourceLineage(repository)
        self._extraction_repository = extraction_repository

    def list_import_batches(self, project_id: str) -> list[ImportBatchRecord]:
        """Ronda 92: lotes de RAG CONTENT importados (procedencia multi-lote)."""
        return self._batch_ledger.list_batches(project_id) if self._batch_ledger else []

    def register_source(self, project_id: str, title: str, source_type, **kwargs) -> Source:
        return self._register.execute(project_id, title, source_type, **kwargs)

    def import_sources_from_folder(
        self, project_id: str, folder_path: str, document_type_code: str = "default",
    ) -> ImportSourcesFromFolderResult:
        """Punto 2 de Validacion_observaciones_RAG_STUDIO.md: alta masiva
        desde la carpeta de entrega de RAG CONTENT STUDIO (manifiesto.csv
        + .md), en vez de archivo por archivo.

        `document_type_code` (Ronda 3, punto 12) etiqueta a todo el lote
        importado con el mismo tipo de documento -- el manifiesto de RAG
        CONTENT no trae esa columna todavía, así que quien importa decide
        el tipo (una carpeta de entrega suele corresponder a un solo tipo
        documental). Sin esto, todas las fuentes importadas quedaban en
        "default", reintroduciendo la mezcla de tipos que el punto 10 ya
        había resuelto para el alta manual."""
        return self._import_from_folder.execute(project_id, folder_path, document_type_code=document_type_code)

    def update_validation_status(self, project_id: str, source_id: str, target_status) -> Source:
        return self._update_status.execute(project_id, source_id, target_status)

    def update_source_details(
        self, project_id: str, source_id: str, title: str, owner_area, access_level, location: str, source_type,
        valid_from: Optional[date] = None, valid_to: Optional[date] = None,
        source_authority: Optional[int] = None, document_type_code: str = "default",
        language: str = "es",
    ) -> Source:
        return self._update_details.execute(
            project_id, source_id, title, owner_area, access_level, location, source_type,
            valid_from=valid_from, valid_to=valid_to, source_authority=source_authority,
            document_type_code=document_type_code, language=language,
        )

    def bulk_set_document_type_code(
        self, project_id: str, source_ids: list[str], document_type_code: str,
    ) -> BulkSetDocumentTypeCodeResult:
        """Ronda 4, punto 4a: corrige en bloque el tipo de documento de
        varias fuentes seleccionadas a la vez -- ver docstring de
        BulkSetDocumentTypeCode sobre por qué no necesita revisar
        extracción (a diferencia de update_source_details)."""
        return self._bulk_set_document_type_code.execute(project_id, source_ids, document_type_code)

    def has_extraction(self, project_id: str, source_id: str) -> bool:
        """Para que la UI sepa, antes de abrir el diálogo de edición, si
        location/source_type deben mostrarse bloqueados (ver
        UpdateSourceDetails/SourceStructuralFieldsLockedError) -- evita
        que el usuario llene el diálogo y se entere del bloqueo solo
        hasta guardar."""
        return self._extraction_repository.get(project_id, source_id) is not None

    def get_source(self, project_id: str, source_id: str) -> Source:
        return self._get.execute(project_id, source_id)

    def list_sources(self, project_id: str) -> list[Source]:
        return self._list.execute(project_id)

    def get_source_lineage(self, project_id: str, source_id: str) -> list[Source]:
        """Pista C.2b del ADR-003: cadena completa de versiones de una
        fuente (supersedes_source_id caminado en ambos sentidos), de
        la más antigua a la más nueva -- incluye la fuente pedida."""
        return self._get_lineage.execute(project_id, source_id)

    def export_source_lineage_as_csv(self, project_id: str, source_id: str) -> str:
        """Pista C.2b del ADR-003: el mismo linaje de get_source_lineage,
        ya formateado como texto CSV -- la UI solo escribe este texto
        en el archivo que el usuario elija, nunca construye el
        formato (ver lineage_export.py)."""
        return format_source_lineage_as_csv(self.get_source_lineage(project_id, source_id))
