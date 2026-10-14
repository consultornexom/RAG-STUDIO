"""Caso de uso: comparar dos proyectos (RAG STUDIO.odt, sección 13).

En Etapa 1 solo compara metadatos administrativos y cantidad de
entradas de configuración: metadatos, fragmentación, reglas, pruebas e
índice (según el comparador completo del documento fuente) todavía no
existen como entidades hasta las Etapas 2-6. Ampliar aquí cuando
existan, sin romper la forma del resultado.
"""
from __future__ import annotations

from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ConfigurationRepository, ProjectRepository


class CompareProjects:
    def __init__(
        self,
        repository: ProjectRepository,
        configuration_repository: ConfigurationRepository,
    ):
        self._repository = repository
        self._configuration_repository = configuration_repository

    def execute(self, project_id_a: str, project_id_b: str) -> dict:
        a = self._repository.get(project_id_a)
        b = self._repository.get(project_id_b)
        if a is None:
            raise ProjectNotFoundError(project_id_a)
        if b is None:
            raise ProjectNotFoundError(project_id_b)

        config_a = self._configuration_repository.list_for_project(project_id_a)
        config_b = self._configuration_repository.list_for_project(project_id_b)

        return {
            "project_a": {"id": a.id, "name": a.name, "status": a.status.value,
                          "configuration_entries": len(config_a)},
            "project_b": {"id": b.id, "name": b.name, "status": b.status.value,
                          "configuration_entries": len(config_b)},
            "same_status": a.status == b.status,
        }
