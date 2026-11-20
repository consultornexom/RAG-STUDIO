"""Ronda 106 (autorizada por NEXOM): ajuste por proyecto "Procedimiento de
recuperación" -- r106 (V + Y + R) o r105b (anterior). Ver
domain.conversational.retrieval_procedure.

Se guarda como entrada versionada de la tabla `configuration` del project.db
(cada cambio agrega una versión: queda el historial), sin migración de
esquema. Viaja con el proyecto a las instantáneas publicadas y a los .agentproj.
"""
from __future__ import annotations

from typing import Optional

from domain.conversational.retrieval_procedure import (
    CONFIGURATION_KEY, DEFAULT_FOR_NEW_PROJECTS, SUPPORTED_PROCEDURES, UnknownRetrievalProcedureError,
    validate_procedure,
)
from domain.projects.entities import ConfigurationEntry
from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ConfigurationRepository, ProjectRepository


class UpdateRetrievalProcedure:
    def __init__(self, repository: ProjectRepository, configuration_repository: ConfigurationRepository):
        self._repository = repository
        self._configuration = configuration_repository

    def execute(self, project_id: str, procedure: str) -> str:
        if procedure not in SUPPORTED_PROCEDURES:
            raise UnknownRetrievalProcedureError(
                f"Procedimiento de recuperación desconocido: {procedure!r} (admitidos: "
                f"{', '.join(SUPPORTED_PROCEDURES)})."
            )
        if self._repository.get(project_id) is None:
            raise ProjectNotFoundError(project_id)
        actual = self._configuration.get_latest(project_id, CONFIGURATION_KEY)
        if actual is not None and actual.value == procedure:
            return procedure
        self._configuration.save(ConfigurationEntry(
            project_id=project_id, key=CONFIGURATION_KEY, value=procedure,
            version=(actual.version + 1) if actual is not None else 1,
        ))
        return procedure


class GetRetrievalProcedure:
    def __init__(self, configuration_repository: ConfigurationRepository):
        self._configuration = configuration_repository

    def execute(self, project_id: str) -> tuple[str, bool]:
        """(procedimiento efectivo, si hay ajuste guardado). Sin ajuste:
        ("r105b", False) -- proyecto anterior a la Ronda 106."""
        entry = self._configuration.get_latest(project_id, CONFIGURATION_KEY)
        guardado: Optional[str] = entry.value if entry is not None else None
        return validate_procedure(guardado), guardado is not None


def set_default_for_new_project(configuration_repository: ConfigurationRepository, project_id: str) -> None:
    """Proyectos NUEVOS (crear, clonar): r106 desde el inicio."""
    configuration_repository.save(ConfigurationEntry(
        project_id=project_id, key=CONFIGURATION_KEY, value=DEFAULT_FOR_NEW_PROJECTS, version=1,
    ))
