"""Caso de uso: generar un respaldo completo de un proyecto."""
from __future__ import annotations

from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.packaging import PackageManifest
from domain.projects.ports import ProjectPackager, ProjectRepository


class BackupProject:
    def __init__(self, repository: ProjectRepository, packager: ProjectPackager):
        self._repository = repository
        self._packager = packager

    def execute(self, project_id: str, destination_path: str) -> PackageManifest:
        if self._repository.get(project_id) is None:
            raise ProjectNotFoundError(project_id)
        return self._packager.backup(project_id, destination_path)
