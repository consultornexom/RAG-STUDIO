"""Caso de uso: archivar un proyecto (transición de estado, no borrado)."""
from __future__ import annotations

from domain.projects.entities import Project, ProjectStatus
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class ArchiveProject:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        archived = project.transition_to(ProjectStatus.ARCHIVADO)
        self._repository.save(archived)
        return archived
