"""Caso de uso: obtener un proyecto por id."""
from __future__ import annotations

from domain.projects.entities import Project
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class GetProject:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project
