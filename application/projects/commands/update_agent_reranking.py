"""Ronda 102 (C4, autorizado por NEXOM): editar el ajuste "Reranking en el
agente" del proyecto (ver Project.agent_reranking). Mismo patrón que
UpdateQualityRegressionThreshold: parámetro técnico, separado de los campos
descriptivos del proyecto."""
from __future__ import annotations

from typing import Optional

from domain.projects.entities import Project
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class UpdateAgentReranking:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str, enabled: Optional[bool]) -> Project:
        """enabled: None = automático (predeterminado), True = activado,
        False = desactivado."""
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("El ajuste de reranking debe ser None, True o False")
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        data = project.model_dump()
        data["agent_reranking"] = enabled
        updated = Project(**data)
        self._repository.save(updated)
        return updated
