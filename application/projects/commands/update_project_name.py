"""Caso de uso: corregir el nombre de un proyecto (Ronda 3, punto 13 de
Validacion_observaciones_RAG_STUDIO.md).

Antes de esto no existía ningún método para actualizar un proyecto ya
creado -- el alta solo pedía el nombre (QInputDialog) y no había forma
de corregir un error de escritura desde la interfaz. Solo se toca el
nombre (mismo alcance mínimo que resolvió el problema reportado); el
resto de los atributos de Project no tienen todavía un caso de uso de
edición porque nadie reportó necesitarlo."""
from __future__ import annotations

from domain.projects.entities import Project
from domain.projects.exceptions import DuplicateProjectError, ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class UpdateProjectName:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str, new_name: str) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        existing = self._repository.get_by_name(new_name)
        if existing is not None and existing.id != project_id:
            raise DuplicateProjectError(new_name)

        # Project.name se valida al construir (_name_no_vacio); reconstruir
        # con Project(**...) en vez de solo model_copy (que no revalida)
        # asegura que ese validador corra igual que en el alta original,
        # mismo criterio ya usado en Project.transition_to().
        data = project.model_dump()
        data["name"] = new_name
        updated = Project(**data)
        self._repository.save(updated)
        return updated
