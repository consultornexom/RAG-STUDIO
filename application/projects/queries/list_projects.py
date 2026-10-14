"""Caso de uso: listar proyectos."""
from __future__ import annotations

from domain.projects.entities import Project
from domain.projects.ports import ProjectRepository


class ListProjects:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, include_archived: bool = True) -> list[Project]:
        return self._repository.list(include_archived=include_archived)
