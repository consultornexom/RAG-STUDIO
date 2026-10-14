"""Puertos del contexto Liberación. Implementados en infrastructure
(ADR-001, sección 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .entities import DeploymentPackage, ProjectSnapshot, ReleaseRecord


class ReleaseRecordRepository(ABC):
    @abstractmethod
    def save(self, record: ReleaseRecord) -> None: ...

    @abstractmethod
    def get(self, project_id: str, record_id: str) -> Optional[ReleaseRecord]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[ReleaseRecord]: ...

    @abstractmethod
    def get_last_record(self, project_id: str) -> Optional[ReleaseRecord]:
        """La liberación más reciente del proyecto -- para saber si la
        última solicitud quedó aprobada, rechazada o bloqueada sin
        tener que recorrer todo el historial."""
        ...


class ReleasePackager(ABC):
    """Ítem 6 de la evaluación de madurez post-8-etapas: genera un
    paquete exportable real (archivos en disco, no solo el JSON en
    línea de `ReleaseRecord.deliverables_report`) con los 8 entregables
    formales de una liberación ya evaluada. `ReleaseRecord` ya trae
    todo lo necesario (checklist, dictamen, entregables, evidencia) --
    este puerto solo lo serializa a disco, no vuelve a calcular nada."""

    @abstractmethod
    def export(self, record: ReleaseRecord, destination_path: str) -> str:
        """Escribe el paquete en `destination_path` y devuelve la ruta
        final (absoluta) donde quedó guardado."""
        ...


class ProjectSnapshotRepository(ABC):
    """Persistencia del historial de instantáneas publicadas de un
    proyecto (ADR-002, Fase 1)."""

    @abstractmethod
    def save(self, snapshot: ProjectSnapshot) -> None: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[ProjectSnapshot]: ...

    @abstractmethod
    def get_latest(self, project_id: str) -> Optional[ProjectSnapshot]: ...


class ProjectSnapshotPublisher(ABC):
    """Copia el estado actual en disco de un proyecto a un directorio
    de solo lectura versionado, separado de projects/<project_id>
    (ADR-002, Fase 1). No decide *cuándo* publicar ni numera la
    versión -- eso es responsabilidad de PublishProjectSnapshot; este
    puerto solo sabe copiar."""

    @abstractmethod
    def publish(self, project_id: str, version: int) -> str:
        """Devuelve la ruta absoluta (str) del directorio publicado."""
        ...


class DeploymentPackager(ABC):
    """Genera el paquete exportable real (.zip) del contexto de la
    Ronda 10 (ver Validacion_observaciones_RAG_STUDIO.md): copia la
    instantánea publicada de un proyecto más los documentos de entrega
    (informe formal, guía de despliegue, plantilla de variables de
    entorno, snippet del widget) ya resueltos en `DeploymentPackage` --
    igual disciplina que `ReleasePackager`: este puerto solo serializa
    a disco lo que `ExportDeploymentPackage` ya calculó, no vuelve a
    calcular nada."""

    @abstractmethod
    def export(self, package: DeploymentPackage, destination_path: str) -> str:
        """Escribe el paquete en `destination_path` y devuelve la ruta
        final (absoluta) donde quedó guardado."""
        ...
