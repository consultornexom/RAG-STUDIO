"""Excepciones del contexto Liberación."""
from __future__ import annotations


class ReleaseDomainError(Exception):
    """Base de las excepciones del contexto Liberación."""


class ReleaseRecordNotFoundError(ReleaseDomainError):
    def __init__(self, project_id: str, record_id: str):
        super().__init__(f"No existe la liberación {record_id!r} en el proyecto {project_id!r}.")


class NoPublishedSnapshotError(ReleaseDomainError):
    """El paquete de entrega al cliente (ExportDeploymentPackage) exige
    una instantánea publicada -- no puede armar un paquete de despliegue
    sin nada que copiar. Distinto de ReleaseRecordNotFoundError: no
    depende en absoluto de haber solicitado ninguna liberación formal
    (mismo criterio que ya usa "Publicar instantánea…", ver
    PublishProjectSnapshot)."""

    def __init__(self, project_id: str):
        super().__init__(
            f"El proyecto {project_id!r} no tiene ninguna instantánea publicada. "
            "Publica una instantánea (\"Publicar instantánea…\") antes de exportar "
            "el paquete de entrega al cliente."
        )
