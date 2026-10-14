"""Caso de uso: publicar una instantánea de solo lectura del estado
actual de un proyecto (Fase 1 del plan de runtime de producción, ver
docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx).

Copia project.db + índice Qdrant (y el resto de projects/<project_id>)
a un directorio versionado separado, para que un futuro runtime pueda
leer un estado certificado sin competir con la app de escritorio por
el lock exclusivo que Qdrant toma sobre su directorio de índice
mientras está abierto.

Deliberadamente independiente de solicitar una liberación formal
(RequestRelease) -- igual criterio que ya usan ExportProject/
BackupProject en el contexto Proyectos: publicar una instantánea no
exige haber pasado las compuertas de calidad, porque publicar un
ambiente de prueba antes de que el proyecto esté listo para liberarse
formalmente es un caso de uso legítimo. Si se publica a partir de un
ReleaseRecord aprobado, su id se conserva como dato de trazabilidad
(`source_release_id`), pero no es un requisito."""
from __future__ import annotations

from typing import Optional

from domain.projects.exceptions import ProjectNotFoundError
from domain.projects.ports import ProjectRepository
from domain.release.entities import ProjectSnapshot
from domain.release.ports import ProjectSnapshotPublisher, ProjectSnapshotRepository


class PublishProjectSnapshot:
    def __init__(
        self, project_repository: ProjectRepository, snapshot_repository: ProjectSnapshotRepository,
        publisher: ProjectSnapshotPublisher,
    ):
        self._project_repository = project_repository
        self._snapshot_repository = snapshot_repository
        self._publisher = publisher

    def execute(self, project_id: str, source_release_id: Optional[str] = None) -> ProjectSnapshot:
        if self._project_repository.get(project_id) is None:
            raise ProjectNotFoundError(project_id)

        previous = self._snapshot_repository.list_for_project(project_id)
        next_version = (max(snapshot.version for snapshot in previous) + 1) if previous else 1

        snapshot_dir = self._publisher.publish(project_id, next_version)

        snapshot = ProjectSnapshot(
            project_id=project_id, version=next_version, source_release_id=source_release_id,
            snapshot_dir=snapshot_dir,
        )
        self._snapshot_repository.save(snapshot)
        return snapshot
