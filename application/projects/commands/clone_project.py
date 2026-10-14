"""Caso de uso: clonar un proyecto existente.

Etapa 1 clona únicamente los metadatos del proyecto (Project). La
clonación de fuentes, fragmentos, índices y reglas se activa cuando
esas entidades existan (Etapas 2+); se documenta como limitación
conocida, no como comportamiento silenciosamente incompleto.
"""
from __future__ import annotations

from domain.projects.entities import Project
from domain.projects.exceptions import DuplicateProjectError, ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class CloneProject:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, source_project_id: str, new_name: str) -> Project:
        source = self._repository.get(source_project_id)
        if source is None:
            raise ProjectNotFoundError(source_project_id)
        if self._repository.get_by_name(new_name) is not None:
            raise DuplicateProjectError(new_name)

        clone = Project(
            name=new_name,
            agent_type_hint=source.agent_type_hint,
            description=source.description,
            domain=source.domain,
            target_users=source.target_users,
            language=source.language,
            risk_level=source.risk_level,
            template_id=source.template_id,
        )
        self._repository.save(clone)
        return clone
