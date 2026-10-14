"""Dobles de prueba en memoria para el contexto Liberación."""
from __future__ import annotations

from typing import Optional

from domain.release.entities import DeploymentPackage, ProjectSnapshot, ReleaseRecord
from domain.release.ports import (
    DeploymentPackager,
    ProjectSnapshotPublisher,
    ProjectSnapshotRepository,
    ReleasePackager,
    ReleaseRecordRepository,
)


class InMemoryReleaseRecordRepository(ReleaseRecordRepository):
    def __init__(self):
        self._records: list[ReleaseRecord] = []

    def save(self, record: ReleaseRecord) -> None:
        self._records.append(record)

    def get(self, project_id: str, record_id: str) -> Optional[ReleaseRecord]:
        return next((r for r in self._records if r.project_id == project_id and r.id == record_id), None)

    def list_for_project(self, project_id: str) -> list[ReleaseRecord]:
        return sorted(
            (r for r in self._records if r.project_id == project_id),
            key=lambda r: r.created_at, reverse=True,
        )

    def get_last_record(self, project_id: str) -> Optional[ReleaseRecord]:
        records = self.list_for_project(project_id)
        return records[0] if records else None


class InMemoryReleasePackager(ReleasePackager):
    """Doble en memoria de ReleasePackager (ítem 6 de la evaluación de
    madurez post-8-etapas) -- no toca el sistema de archivos real,
    solo registra la llamada para que las pruebas puedan afirmar qué
    se le pidió exportar."""

    def __init__(self):
        self.calls: list[tuple[ReleaseRecord, str]] = []

    def export(self, record: ReleaseRecord, destination_path: str) -> str:
        self.calls.append((record, destination_path))
        return destination_path


class InMemoryProjectSnapshotRepository(ProjectSnapshotRepository):
    """ADR-002, Fase 1 -- mismo patrón que InMemoryReleaseRecordRepository."""

    def __init__(self):
        self._snapshots: list[ProjectSnapshot] = []

    def save(self, snapshot: ProjectSnapshot) -> None:
        self._snapshots.append(snapshot)

    def list_for_project(self, project_id: str) -> list[ProjectSnapshot]:
        return sorted(
            (s for s in self._snapshots if s.project_id == project_id),
            key=lambda s: s.version, reverse=True,
        )

    def get_latest(self, project_id: str) -> Optional[ProjectSnapshot]:
        snapshots = self.list_for_project(project_id)
        return snapshots[0] if snapshots else None


class FakeProjectSnapshotPublisher(ProjectSnapshotPublisher):
    """No toca el sistema de archivos real -- solo registra la llamada
    y devuelve una ruta ficticia, para que las pruebas de la fachada no
    dependan de infrastructure (esa parte se prueba por separado contra
    el filesystem real, ver tests/unit/infrastructure)."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def publish(self, project_id: str, version: int) -> str:
        self.calls.append((project_id, version))
        return f"/fake/snapshots/{project_id}/v{version}"


class InMemoryDeploymentPackager(DeploymentPackager):
    """Doble en memoria de DeploymentPackager (Ronda 10) -- mismo
    criterio que InMemoryReleasePackager: no toca el sistema de
    archivos real, solo registra qué se le pidió exportar."""

    def __init__(self):
        self.calls: list[tuple[DeploymentPackage, str]] = []

    def export(self, package: DeploymentPackage, destination_path: str) -> str:
        self.calls.append((package, destination_path))
        return destination_path
