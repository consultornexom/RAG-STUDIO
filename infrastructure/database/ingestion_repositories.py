"""Implementaciones concretas de ExtractionRepository, ChunkRepository
y FragmentationPolicyRepository (ADR-001, sección 4)."""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy import delete, select

from domain.ingestion.entities import Chunk, ChunkType, ExtractionRecord, FragmentationPolicy, FragmentationStrategy
from domain.ingestion.ports import ChunkRepository, ExtractionRepository, FragmentationPolicyRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import ChunkRecord, ExtractionRecordHistoryRecord, ExtractionRecordRecord, FragmentationPolicyRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyExtractionRepository(ExtractionRepository):
    """save() mantiene el upsert de siempre en extraction_record (la
    extracción vigente, la que lee get()) y además agrega una fila en
    extraction_record_history (tabla aparte, de solo inserción) en
    cada llamada -- ítem 5 de la evaluación de madurez
    post-8-etapas."""

    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, record: ExtractionRecord) -> None:
        with _session_factory_for(self._paths, record.project_id)() as session:
            existing = session.execute(
                select(ExtractionRecordRecord).where(ExtractionRecordRecord.source_id == record.source_id)
            ).scalars().first()
            if existing is None:
                session.add(ExtractionRecordRecord(
                    id=record.id, project_id=record.project_id, source_id=record.source_id, text=record.text,
                    page_breaks=json.dumps(record.page_breaks), extraction_method=record.extraction_method,
                    warnings=json.dumps(record.warnings),
                    structured_blocks=json.dumps(record.structured_blocks),
                    extracted_at=record.extracted_at,
                ))
            else:
                existing.text = record.text
                existing.page_breaks = json.dumps(record.page_breaks)
                existing.extraction_method = record.extraction_method
                existing.warnings = json.dumps(record.warnings)
                existing.structured_blocks = json.dumps(record.structured_blocks)
                existing.extracted_at = record.extracted_at
            # Historial: id propio (no reutiliza record.id) para no
            # depender de que quien llame genere siempre un id distinto
            # por intento -- ver docstring de ExtractionRecordHistoryRecord.
            session.add(ExtractionRecordHistoryRecord(
                id=str(uuid.uuid4()), project_id=record.project_id, source_id=record.source_id,
                text=record.text, page_breaks=json.dumps(record.page_breaks),
                extraction_method=record.extraction_method, warnings=json.dumps(record.warnings),
                structured_blocks=json.dumps(record.structured_blocks),
                extracted_at=record.extracted_at,
            ))
            session.commit()

    def get(self, project_id: str, source_id: str) -> Optional[ExtractionRecord]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(ExtractionRecordRecord).where(ExtractionRecordRecord.source_id == source_id)
            ).scalars().first()
            if record is None or record.project_id != project_id:
                return None
            return ExtractionRecord(
                id=record.id, project_id=record.project_id, source_id=record.source_id, text=record.text,
                page_breaks=json.loads(record.page_breaks), extraction_method=record.extraction_method,
                warnings=json.loads(record.warnings),
                # Filas creadas antes de la migración 0015 quedan en
                # NULL -- sin backfill, se leen como "sin bloques
                # estructurados" (mismo criterio que structured_content
                # en ChunkRecord).
                structured_blocks=(
                    json.loads(record.structured_blocks) if record.structured_blocks is not None else {}
                ),
                extracted_at=record.extracted_at,
            )

    def list_history(self, project_id: str, source_id: str) -> list[ExtractionRecord]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ExtractionRecordHistoryRecord).where(
                    ExtractionRecordHistoryRecord.project_id == project_id,
                    ExtractionRecordHistoryRecord.source_id == source_id,
                ).order_by(ExtractionRecordHistoryRecord.extracted_at.desc())
            ).scalars().all()
            return [
                ExtractionRecord(
                    id=r.id, project_id=r.project_id, source_id=r.source_id, text=r.text,
                    page_breaks=json.loads(r.page_breaks), extraction_method=r.extraction_method,
                    warnings=json.loads(r.warnings),
                    structured_blocks=(
                        json.loads(r.structured_blocks) if r.structured_blocks is not None else {}
                    ),
                    extracted_at=r.extracted_at,
                )
                for r in records
            ]


class SqlAlchemyChunkRepository(ChunkRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save_many(self, project_id: str, chunks: list[Chunk]) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            for chunk in chunks:
                session.add(_chunk_record_from(chunk))
            session.commit()

    def replace_for_source(self, project_id: str, source_id: str, chunks: list[Chunk]) -> None:
        # Auditoría profunda (ronda posterior a la 76, ver bitácora):
        # borrado + inserción en la MISMA sesión/transacción -- un solo
        # commit al final, a diferencia de delete_for_source() +
        # save_many() por separado (dos transacciones independientes).
        # Si algo falla antes de este commit, la sesión completa se
        # revierte (comportamiento por defecto de SQLAlchemy al salir
        # del `with` sin haber llamado a session.commit()) y los chunks
        # anteriores de esta fuente quedan intactos.
        with _session_factory_for(self._paths, project_id)() as session:
            session.execute(
                delete(ChunkRecord).where(ChunkRecord.project_id == project_id, ChunkRecord.source_id == source_id)
            )
            for chunk in chunks:
                session.add(_chunk_record_from(chunk))
            session.commit()

    def list_for_source(self, project_id: str, source_id: str) -> list[Chunk]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ChunkRecord)
                .where(ChunkRecord.project_id == project_id, ChunkRecord.source_id == source_id)
                .order_by(ChunkRecord.chunk_index)
            ).scalars().all()
            return [_record_to_chunk(r) for r in records]

    def list_for_project(self, project_id: str) -> list[Chunk]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ChunkRecord)
                .where(ChunkRecord.project_id == project_id)
                .order_by(ChunkRecord.source_id, ChunkRecord.chunk_index)
            ).scalars().all()
            return [_record_to_chunk(r) for r in records]

    def get(self, project_id: str, chunk_id: str) -> Optional[Chunk]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(ChunkRecord, chunk_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_chunk(record)

    def delete_for_source(self, project_id: str, source_id: str) -> None:
        with _session_factory_for(self._paths, project_id)() as session:
            session.execute(
                delete(ChunkRecord).where(ChunkRecord.project_id == project_id, ChunkRecord.source_id == source_id)
            )
            session.commit()


def _chunk_record_from(chunk: Chunk) -> ChunkRecord:
    """Factorizado de save_many()/replace_for_source() (auditoría
    posterior a la Ronda 76) -- misma construcción de fila, para que
    replace_for_source() no duplique esta lista de columnas."""
    return ChunkRecord(
        id=chunk.id, project_id=chunk.project_id, source_id=chunk.source_id,
        chunk_index=chunk.chunk_index, text=chunk.text, token_count=chunk.token_count,
        section_title=chunk.section_title, page_start=chunk.page_start, page_end=chunk.page_end,
        chunk_type=chunk.chunk_type.value, previous_chunk_id=chunk.previous_chunk_id,
        next_chunk_id=chunk.next_chunk_id, parent_chunk_id=chunk.parent_chunk_id,
        structured_content=(
            json.dumps(chunk.structured_content) if chunk.structured_content is not None else None
        ),
        semantic_summary=chunk.semantic_summary,
        inherited_metadata=json.dumps(chunk.inherited_metadata),
        pipeline_version=chunk.pipeline_version, created_at=chunk.created_at,
        image_relative_path=chunk.image_relative_path,
    )


def _record_to_chunk(record: ChunkRecord) -> Chunk:
    return Chunk(
        id=record.id, project_id=record.project_id, source_id=record.source_id, chunk_index=record.chunk_index,
        text=record.text, token_count=record.token_count, section_title=record.section_title,
        page_start=record.page_start, page_end=record.page_end, chunk_type=ChunkType(record.chunk_type),
        previous_chunk_id=record.previous_chunk_id, next_chunk_id=record.next_chunk_id,
        parent_chunk_id=record.parent_chunk_id,
        structured_content=(
            json.loads(record.structured_content) if record.structured_content is not None else None
        ),
        semantic_summary=record.semantic_summary, inherited_metadata=json.loads(record.inherited_metadata),
        pipeline_version=record.pipeline_version, created_at=record.created_at,
        image_relative_path=record.image_relative_path,
    )


class SqlAlchemyFragmentationPolicyRepository(FragmentationPolicyRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save_policy(self, policy: FragmentationPolicy) -> None:
        with _session_factory_for(self._paths, policy.project_id)() as session:
            existing = session.execute(
                select(FragmentationPolicyRecord).where(
                    FragmentationPolicyRecord.project_id == policy.project_id,
                    FragmentationPolicyRecord.document_type_code == policy.document_type_code,
                )
            ).scalars().first()
            if existing is None:
                session.add(FragmentationPolicyRecord(
                    id=policy.id, project_id=policy.project_id, document_type_code=policy.document_type_code,
                    strategy=policy.strategy.value, target_tokens=policy.target_tokens,
                    overlap_tokens=policy.overlap_tokens, min_tokens=policy.min_tokens,
                    created_at=policy.created_at,
                ))
            else:
                existing.strategy = policy.strategy.value
                existing.target_tokens = policy.target_tokens
                existing.overlap_tokens = policy.overlap_tokens
                existing.min_tokens = policy.min_tokens
            session.commit()

    def get_policy(self, project_id: str, document_type_code: str) -> Optional[FragmentationPolicy]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(FragmentationPolicyRecord).where(
                    FragmentationPolicyRecord.project_id == project_id,
                    FragmentationPolicyRecord.document_type_code == document_type_code,
                )
            ).scalars().first()
            if record is None:
                return None
            return _record_to_policy(record)

    def list_policies(self, project_id: str) -> list[FragmentationPolicy]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(FragmentationPolicyRecord).where(FragmentationPolicyRecord.project_id == project_id)
            ).scalars().all()
            return [_record_to_policy(r) for r in records]


def _record_to_policy(record: FragmentationPolicyRecord) -> FragmentationPolicy:
    return FragmentationPolicy(
        id=record.id, project_id=record.project_id, document_type_code=record.document_type_code,
        strategy=FragmentationStrategy(record.strategy), target_tokens=record.target_tokens,
        overlap_tokens=record.overlap_tokens, min_tokens=record.min_tokens, created_at=record.created_at,
    )
