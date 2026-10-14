"""Caso de uso: editar el umbral de la compuerta de liberación
"Regresión de recuperación" (Ronda 53, Propuesta de evaluación continua
reforzada, opción B' confirmada por el consultor).

Deliberadamente separado de UpdateProjectDetails: ese caso de uso edita
los siete campos descriptivos de Project, deliberadamente genéricos
(ver domain/projects/entities.py y ui/projects/panel.py::
_ProjectDetailsDialog) -- este es un parámetro técnico del motor de
evaluación continua, no un campo descriptivo del proyecto, y se edita
desde el panel de Calidad, no desde el diálogo de detalles del
proyecto. Mismo patrón de fetch -> reconstruir vía Project(**data)
(revalida el rango 0.0-1.0) -> guardar que ya usan UpdateProjectName y
UpdateProjectDetails."""
from __future__ import annotations

from typing import Optional

from domain.projects.entities import Project
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class UpdateQualityRegressionThreshold:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str, threshold: Optional[float]) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        data = project.model_dump()
        data["quality_regression_threshold"] = threshold
        updated = Project(**data)
        self._repository.save(updated)
        return updated
