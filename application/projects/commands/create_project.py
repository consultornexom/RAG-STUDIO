"""Caso de uso: crear un proyecto (Módulo 1 — RAG STUDIO.odt, sección 8)."""
from __future__ import annotations

from typing import Optional

from domain.projects.entities import Project
from domain.projects.exceptions import DuplicateProjectError
from domain.projects.ports import ProjectRepository


class CreateProject:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(
        self,
        name: str,
        agent_type_hint: Optional[str] = None,
        description: str = "",
        domain: Optional[str] = None,
        target_users: Optional[str] = None,
        language: str = "es",
        risk_level: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Project:
        if self._repository.get_by_name(name) is not None:
            raise DuplicateProjectError(name)
        project = Project(
            name=name,
            agent_type_hint=agent_type_hint,
            description=description,
            domain=domain,
            target_users=target_users,
            language=language,
            risk_level=risk_level,
            template_id=template_id,
        )
        self._repository.save(project)
        return project
