"""Caso de uso: eliminar un proyecto vacío (Ronda 3, punto 13 de
Validacion_observaciones_RAG_STUDIO.md).

Antes de esto la única operación disponible sobre un proyecto existente
era "Archivar" (ArchiveProject) -- una transición de estado permanente,
sin eliminación real. Se agrega borrado real, pero bloqueado con el
mismo criterio ya usado para campos y catálogos (FieldInUseError,
CatalogInUseError): solo se permite eliminar un proyecto que todavía no
tiene ninguna fuente registrada. Un proyecto con fuentes reales sigue
teniendo que pasar por "Archivar" -- eliminar ahí sí perdería trabajo
real sin posibilidad de recuperación, distinto del caso de un proyecto
creado por error y nunca usado.

Depende de SourceRepository (contexto Documentos) desde el contexto
Proyectos -- mismo patrón cruzado ya usado en
application/metadata/commands/delete_field_definition.py, que depende
de SourceRepository y SourceMetadataRepository desde Metadatos."""
from __future__ import annotations

from domain.documents.ports import SourceRepository
from domain.projects.exceptions import ProjectInUseError, ProjectNotFoundError
from domain.projects.ports import ProjectRepository


class DeleteProject:
    def __init__(self, repository: ProjectRepository, source_repository: SourceRepository):
        self._repository = repository
        self._source_repository = source_repository

    def execute(self, project_id: str) -> None:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        sources = self._source_repository.list_for_project(project_id)
        if sources:
            raise ProjectInUseError(project_id, len(sources))

        self._repository.delete(project_id)
