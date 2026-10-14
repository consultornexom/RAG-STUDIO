"""Implementación concreta de PipelineRunRepository (ADR-001, sección
4)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select

from domain.pipeline.entities import PipelineItemStatus, PipelineRun, PipelineRunItem, PipelineRunStatus
from domain.pipeline.ports import PipelineRunRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import PipelineRunItemRecord, PipelineRunRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyPipelineRunRepository(PipelineRunRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, run: PipelineRun) -> None:
        # A diferencia de la mayoría de los repositorios de este
        # proyecto (upsert por id), PipelineRun se guarda completa cada
        # vez -- RunPipeline llama a save() una sola vez, al terminar
        # la corrida (o al cancelarla), nunca a medio camino, así que no
        # hace falta un upsert incremental por item.
        with _session_factory_for(self._paths, run.project_id)() as session:
            session.add(PipelineRunRecord(
                id=run.id, project_id=run.project_id, document_type_code=run.document_type_code,
                status=run.status.value, started_at=run.started_at, finished_at=run.finished_at,
            ))
            for item in run.items:
                session.add(PipelineRunItemRecord(
                    id=item.id, run_id=run.id, project_id=run.project_id, source_id=item.source_id,
                    source_title=item.source_title, status=item.status.value, content_hash=item.content_hash,
                    steps_completed=json.dumps(item.steps_completed), chunks_indexed=item.chunks_indexed,
                    warnings=json.dumps(item.warnings), error=item.error,
                    started_at=item.started_at, finished_at=item.finished_at,
                ))
            session.commit()

    def get(self, project_id: str, run_id: str) -> Optional[PipelineRun]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(PipelineRunRecord, run_id)
            if record is None or record.project_id != project_id:
                return None
            item_records = session.execute(
                select(PipelineRunItemRecord)
                .where(PipelineRunItemRecord.run_id == run_id)
                .order_by(PipelineRunItemRecord.started_at)
            ).scalars().all()
            return _record_to_run(record, item_records)

    def list_for_project(self, project_id: str) -> list[PipelineRun]:
        with _session_factory_for(self._paths, project_id)() as session:
            run_records = session.execute(
                select(PipelineRunRecord)
                .where(PipelineRunRecord.project_id == project_id)
                .order_by(PipelineRunRecord.started_at.desc())
            ).scalars().all()
            runs = []
            for run_record in run_records:
                item_records = session.execute(
                    select(PipelineRunItemRecord)
                    .where(PipelineRunItemRecord.run_id == run_record.id)
                    .order_by(PipelineRunItemRecord.started_at)
                ).scalars().all()
                runs.append(_record_to_run(run_record, item_records))
            return runs

    def get_last_successful_item(self, project_id: str, source_id: str) -> Optional[PipelineRunItem]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(PipelineRunItemRecord)
                .where(
                    PipelineRunItemRecord.project_id == project_id,
                    PipelineRunItemRecord.source_id == source_id,
                    PipelineRunItemRecord.status == PipelineItemStatus.EXITOSO.value,
                )
                .order_by(PipelineRunItemRecord.started_at.desc())
            ).scalars().first()
            if record is None:
                return None
            return _record_to_item(record)


def _record_to_run(record: PipelineRunRecord, item_records: list[PipelineRunItemRecord]) -> PipelineRun:
    return PipelineRun(
        id=record.id, project_id=record.project_id, document_type_code=record.document_type_code,
        status=PipelineRunStatus(record.status), items=[_record_to_item(r) for r in item_records],
        started_at=record.started_at, finished_at=record.finished_at,
    )


def _record_to_item(record: PipelineRunItemRecord) -> PipelineRunItem:
    return PipelineRunItem(
        id=record.id, source_id=record.source_id, source_title=record.source_title,
        status=PipelineItemStatus(record.status), content_hash=record.content_hash,
        steps_completed=json.loads(record.steps_completed), chunks_indexed=record.chunks_indexed,
        warnings=json.loads(record.warnings), error=record.error,
        started_at=record.started_at, finished_at=record.finished_at,
    )
