"""Caso de uso: mover el estado de un Project a través del grafo de
transiciones que el dominio ya valida (Ronda 15, punto 48).

Antes de esto, la única transición con un control propio en la interfaz
era "Archivar" (ArchiveProject, siempre hacia ARCHIVADO). Las otras
transiciones del grafo (`Project.allowed_next_statuses()`,
`domain/projects/entities.py`) no tenían ningún comando de application
que las expusiera, aunque `transition_to()` ya las validaba.

Este comando no inventa ninguna política nueva: solo hace visible, capa
por capa (application -> ui), el mismo grafo que el dominio ya impone.
No reemplaza compuertas de liberación (RequestRelease/EvaluateReleaseGates
siguen siendo el mecanismo de negocio para decidir si un proyecto debería
liberarse); simplemente permite mover manualmente el campo `status`
cuando el operador decide hacerlo, tal como ya podía hacer con
"Archivar"."""
from __future__ import annotations

from domain.projects.entities import Project, ProjectStatus
from domain.projects.exceptions import InvalidStatusTransitionError, ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class ChangeProjectStatus:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(self, project_id: str, target_status: str) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        try:
            target = ProjectStatus(target_status)
        except ValueError as exc:
            # Un valor que no corresponde a ningún ProjectStatus conocido
            # se trata igual que una transición inválida: desde el punto
            # de vista de quien llama, "liberado_bien" no es una transición
            # válida por el mismo motivo que "archivado -> inicial" no lo
            # es. Evita introducir una excepción nueva solo para este caso.
            raise InvalidStatusTransitionError(project.status.value, target_status) from exc

        updated = project.transition_to(target)
        self._repository.save(updated)
        return updated
