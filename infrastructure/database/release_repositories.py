"""Implementación concreta del repositorio del contexto Liberación
(ADR-001, sección 4)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select

from domain.release.entities import ProjectSnapshot, ReleaseChecklist, ReleaseRecord, ReleaseStatus
from domain.release.ports import ProjectSnapshotRepository, ReleaseRecordRepository
from infrastructure.filesystem.paths import InstallationPaths

from .engine import make_session_factory, make_sqlite_engine
from .migrations import ensure_project_db
from .models import ProjectSnapshotRecord, ReleaseRecordRecord


def _session_factory_for(paths: InstallationPaths, project_id: str):
    db_path = ensure_project_db(paths, project_id)
    return make_session_factory(make_sqlite_engine(db_path))


class SqlAlchemyReleaseRecordRepository(ReleaseRecordRepository):
    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, record: ReleaseRecord) -> None:
        # Igual que PipelineRunRepository/EvaluationRunRepository: se
        # guarda completo cada vez, cada solicitud de liberación es una
        # entrada nueva en el historial (nunca se sobreescribe).
        with _session_factory_for(self._paths, record.project_id)() as session:
            session.add(ReleaseRecordRecord(
                id=record.id, project_id=record.project_id, status=record.status.value,
                checklist=record.checklist.model_dump_json(),
                dictamen=record.dictamen, evidence=json.dumps(record.evidence),
                deliverables_report=json.dumps(record.deliverables_report),
                created_at=record.created_at,
            ))
            session.commit()

    def get(self, project_id: str, record_id: str) -> Optional[ReleaseRecord]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.get(ReleaseRecordRecord, record_id)
            if record is None or record.project_id != project_id:
                return None
            return _record_to_release_record(record)

    def list_for_project(self, project_id: str) -> list[ReleaseRecord]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ReleaseRecordRecord)
                .where(ReleaseRecordRecord.project_id == project_id)
                .order_by(ReleaseRecordRecord.created_at.desc())
            ).scalars().all()
            return [_record_to_release_record(record) for record in records]

    def get_last_record(self, project_id: str) -> Optional[ReleaseRecord]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(ReleaseRecordRecord)
                .where(ReleaseRecordRecord.project_id == project_id)
                .order_by(ReleaseRecordRecord.created_at.desc())
            ).scalars().first()
            return None if record is None else _record_to_release_record(record)


def _record_to_release_record(record: ReleaseRecordRecord) -> ReleaseRecord:
    return ReleaseRecord(
        id=record.id, project_id=record.project_id, status=ReleaseStatus(record.status),
        checklist=ReleaseChecklist.model_validate_json(record.checklist),
        dictamen=record.dictamen, evidence=json.loads(record.evidence),
        deliverables_report=json.loads(record.deliverables_report),
        created_at=record.created_at,
    )


class SqlAlchemyProjectSnapshotRepository(ProjectSnapshotRepository):
    """ADR-002, Fase 1. Mismo patrón que SqlAlchemyReleaseRecordRepository:
    cada instantánea publicada es una fila nueva, nunca se sobreescribe."""

    def __init__(self, paths: InstallationPaths):
        self._paths = paths

    def save(self, snapshot: ProjectSnapshot) -> None:
        with _session_factory_for(self._paths, snapshot.project_id)() as session:
            session.add(ProjectSnapshotRecord(
                id=snapshot.id, project_id=snapshot.project_id, version=snapshot.version,
                source_release_id=snapshot.source_release_id, snapshot_dir=snapshot.snapshot_dir,
                created_at=snapshot.created_at,
            ))
            session.commit()

    def list_for_project(self, project_id: str) -> list[ProjectSnapshot]:
        with _session_factory_for(self._paths, project_id)() as session:
            records = session.execute(
                select(ProjectSnapshotRecord)
                .where(ProjectSnapshotRecord.project_id == project_id)
                .order_by(ProjectSnapshotRecord.version.desc())
            ).scalars().all()
            return [_record_to_snapshot(record) for record in records]

    def get_latest(self, project_id: str) -> Optional[ProjectSnapshot]:
        with _session_factory_for(self._paths, project_id)() as session:
            record = session.execute(
                select(ProjectSnapshotRecord)
                .where(ProjectSnapshotRecord.project_id == project_id)
                .order_by(ProjectSnapshotRecord.version.desc())
            ).scalars().first()
            return None if record is None else _record_to_snapshot(record)


def _record_to_snapshot(record: ProjectSnapshotRecord) -> ProjectSnapshot:
    return ProjectSnapshot(
        id=record.id, project_id=record.project_id, version=record.version,
        source_release_id=record.source_release_id, snapshot_dir=record.snapshot_dir,
        created_at=record.created_at,
    )
