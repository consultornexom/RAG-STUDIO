"""Implementación concreta de SourceRepository (ADR-001, sección 4)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import select

from domain.documents.entities import AccessLevel, Source, SourceType, SourceValidationStatus
from domain.documents.manifest import extraer_nombre_base_multiplataforma
from domain.documents.ports import SourceRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import SourceRecord


def _source_to_record(source: Source) -> SourceRecord:
    return SourceRecord(
        id=source.id, project_id=source.project_id, title=source.title,
        source_type=source.source_type.value, location=source.location,
        owner_area=source.owner_area, access_level=source.access_level.value,
        language=source.language, version=source.version, content_hash=source.content_hash,
        validation_status=source.validation_status.value, valid_from=source.valid_from,
        valid_to=source.valid_to, source_authority=source.source_authority,
        supersedes_source_id=source.supersedes_source_id, original_copy_path=source.original_copy_path,
        document_type_code=source.document_type_code,
        created_at=source.created_at, updated_at=source.updated_at,
    )


def _record_to_source(record: SourceRecord) -> Source:
    return Source(
        id=record.id, project_id=record.project_id, title=record.title,
        source_type=SourceType(record.source_type), location=record.location,
        owner_area=record.owner_area, access_level=AccessLevel(record.access_level),
        language=record.language, version=record.version, content_hash=record.content_hash,
        validation_status=SourceValidationStatus(record.validation_status),
        valid_from=record.valid_from, valid_to=record.valid_to,
        source_authority=record.source_authority, supersedes_source_id=record.supersedes_source_id,
        original_copy_path=record.original_copy_path,
        document_type_code=record.document_type_code,
        created_at=record.created_at, updated_at=record.updated_at,
    )


class SqlAlchemySourceRepository(SourceRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def _portable(self, source: Source) -> Source:
        """Ronda 92 (portabilidad entre equipos, SOLICITUD NEXOM): la copia
        de respaldo de cada fuente vive en `<proyecto>/sources/original/`,
        pero `original_copy_path` se guarda como ruta ABSOLUTA del equipo
        donde se registró. Al llevar el proyecto (.agentproj) o una
        instantánea a otro equipo/carpeta, esa ruta deja de existir y la
        re-extracción o el indexado de imágenes fallaban aunque la copia
        sí viajó. Si la ruta guardada no existe aquí, se usa el mismo
        archivo dentro de la carpeta ACTUAL del proyecto. Nunca se adivina
        otro archivo: solo el mismo nombre en sources/original/."""
        guardada = source.original_copy_path
        if not guardada or Path(guardada).exists():
            return source
        nombre = extraer_nombre_base_multiplataforma(guardada)
        if not nombre:
            return source
        try:
            local = self._paths.project_dir(source.project_id) / "sources" / "original" / nombre
        except ValueError:
            return source
        if not local.is_file():
            return source
        return source.model_copy(update={"original_copy_path": str(local)})

    def _session_factory(self, project_id: str):
        db_path = ensure_project_db(self._paths, project_id)
        return make_session_factory(make_sqlite_engine(db_path))

    def save(self, source: Source) -> None:
        with self._session_factory(source.project_id)() as session:
            existing = session.get(SourceRecord, source.id)
            if existing is None:
                session.add(_source_to_record(source))
            else:
                for field in (
                    "title", "source_type", "location", "owner_area", "access_level", "language",
                    "version", "content_hash", "validation_status", "valid_from", "valid_to",
                    "source_authority", "supersedes_source_id", "original_copy_path",
                    "document_type_code", "updated_at",
                ):
                    value = getattr(source, field)
                    if hasattr(value, "value"):  # enums
                        value = value.value
                    setattr(existing, field, value)
            session.commit()

    def get(self, project_id: str, source_id: str) -> Optional[Source]:
        with self._session_factory(project_id)() as session:
            record = session.get(SourceRecord, source_id)
            return self._portable(_record_to_source(record)) if record else None

    def get_by_content_hash(self, project_id: str, content_hash: str) -> Optional[Source]:
        with self._session_factory(project_id)() as session:
            record = session.execute(
                select(SourceRecord).where(
                    SourceRecord.project_id == project_id, SourceRecord.content_hash == content_hash
                )
            ).scalars().first()
            return self._portable(_record_to_source(record)) if record else None

    def list_for_project(self, project_id: str) -> list[Source]:
        with self._session_factory(project_id)() as session:
            records = session.execute(
                select(SourceRecord).where(SourceRecord.project_id == project_id)
            ).scalars().all()
            return [self._portable(_record_to_source(r)) for r in records]
