"""Caso de uso: editar los siete campos descriptivos de un Project ya
creado (Ronda 15, punto 48 de Validacion_observaciones_RAG_STUDIO.md).

CreateProject.execute() ya aceptaba estos siete campos como kwargs desde
su implementación original; lo que faltaba era una forma de corregirlos
después del alta, sin pasar por un borrado/recreación. Mismo patrón que
UpdateProjectName: fetch -> reconstruir vía Project(**data) (revalida
los validadores del modelo, a diferencia de model_copy) -> guardar.

Solo toca los siete campos descriptivos; nunca el estado (eso es
ChangeProjectStatus, un caso de uso separado porque tiene sus propias
reglas de transición) ni el nombre (eso sigue siendo UpdateProjectName,
que además valida duplicados)."""
from __future__ import annotations

from typing import Optional

from domain.projects.entities import Project
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository

# Los únicos campos editables por este caso de uso: los siete campos
# descriptivos que ya acepta CreateProject. Una lista explícita evita
# que alguien cuele aquí "status" o "name" por accidente al llamar con
# **kwargs desde la UI.
_CAMPOS_EDITABLES = (
    "agent_type_hint",
    "description",
    "domain",
    "target_users",
    "language",
    "risk_level",
    "template_id",
)


class UpdateProjectDetails:
    def __init__(self, repository: ProjectRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        agent_type_hint: Optional[str] = None,
        description: Optional[str] = None,
        domain: Optional[str] = None,
        target_users: Optional[str] = None,
        language: Optional[str] = None,
        risk_level: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        valores = {
            "agent_type_hint": agent_type_hint,
            "description": description,
            "domain": domain,
            "target_users": target_users,
            "language": language,
            "risk_level": risk_level,
            "template_id": template_id,
        }
        data = project.model_dump()
        for campo in _CAMPOS_EDITABLES:
            valor = valores[campo]
            if valor is not None:
                data[campo] = valor

        updated = Project(**data)
        self._repository.save(updated)
        return updated
