"""Caso de uso: listar las instantáneas publicadas de un proyecto
(ADR-002, Fase 1) -- mismo criterio que ListReleaseRecords."""
from __future__ import annotations

from domain.release.entities import ProjectSnapshot
from domain.release.ports import ProjectSnapshotRepository


class ListProjectSnapshots:
    def __init__(self, repository: ProjectSnapshotRepository):
        self._repository = repository

    def execute(self, project_id: str) -> list[ProjectSnapshot]:
        return self._repository.list_for_project(project_id)
