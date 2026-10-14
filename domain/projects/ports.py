"""Puertos (interfaces) del contexto Proyectos.

Definidos en domain e implementados en infrastructure (ADR-001,
sección 4). domain nunca importa la implementación concreta, solo
depende de estas abstracciones.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Optional

from .entities import ConfigurationEntry, IdentityPolicy, Project
from .packaging import IntegrityReport, PackageManifest


class ProjectRepository(ABC):
    """Persistencia de proyectos en la base global (application.db)."""

    @abstractmethod
    def save(self, project: Project) -> None: ...

    @abstractmethod
    def get(self, project_id: str) -> Optional[Project]: ...

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Project]: ...

    @abstractmethod
    def list(self, include_archived: bool = True) -> list[Project]: ...

    @abstractmethod
    def delete(self, project_id: str) -> None: ...


class ConfigurationRepository(ABC):
    """Persistencia de configuración versionada por proyecto."""

    @abstractmethod
    def save(self, entry: ConfigurationEntry) -> None: ...

    @abstractmethod
    def get_latest(self, project_id: str, key: str) -> Optional[ConfigurationEntry]: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[ConfigurationEntry]: ...


class ProjectPackager(ABC):
    """Empaquetado portable .agentproj: exportar, importar, verificar.

    Cubre las funciones de Módulo 1 (RAG STUDIO.odt, sección 8):
    Exportar, Importar, Validar integridad, Generar respaldo.
    """

    @abstractmethod
    def export(
        self,
        project_id: str,
        destination_path: str,
        include_documents: bool = True,
    ) -> PackageManifest: ...

    @abstractmethod
    def import_project(
        self, package_path: str, new_project_id: Optional[str] = None, new_name: Optional[str] = None,
        identity_policy: IdentityPolicy = IdentityPolicy.PRESERVE,
    ) -> Project:
        """RAG-INC-01a: con FORK, la copia temporal recibe un
        `knowledge_base_id` nuevo y un `lineage_id` nuevo por familia ANTES
        de quedar visible; con PRESERVE se conservan tal cual. Quien decide
        la política y verifica colisiones es ImportProject."""
        ...

    @abstractmethod
    def read_knowledge_base_id(self, package_path: str) -> Optional[str]:
        """RAG-INC-01a: `knowledge_base_id` que trae el paquete, leído sin
        escribir nada en la instalación. None si el paquete es anterior a la
        migración 0021 (la identidad se asignará al migrarlo)."""
        ...

    # Ronda 88 (2026-10-02): operaciones que ImportProject necesita para
    # comprobar colisiones ANTES de copiar nada y para deshacer una
    # importación que no se pudo registrar.
    @abstractmethod
    def inspect_package(self, package_path: str) -> PackageManifest:
        """Manifiesto de un paquete (sin escribir nada en disco)."""
        ...

    @abstractmethod
    def has_project_data(self, project_id: str) -> bool:
        """True si ya hay archivos del proyecto en disco."""
        ...

    @abstractmethod
    def quarantine_project_data(self, project_id: str) -> str:
        """Aparta (mueve, no borra) los archivos de un proyecto no
        registrado; devuelve la ruta nueva."""
        ...

    @abstractmethod
    def discard_project_data(self, project_id: str) -> None:
        """Borra los archivos recién importados de un proyecto que no se
        pudo registrar."""
        ...

    @abstractmethod
    def verify_integrity(self, package_path: str) -> IntegrityReport: ...

    @abstractmethod
    def backup(self, project_id: str, destination_path: str) -> PackageManifest:
        """Genera un respaldo completo (equivalente a export con documentos)."""
        ...


class ImportLock(ABC):
    """RAG-INC-01a (Alcance, INC01-R9): exclusión mutua ENTRE PROCESOS para la
    secuencia comprobar → importar → registrar. Un bloqueo real del sistema
    operativo, con tiempo máximo (ImportLockTimeoutError) y liberado
    automáticamente si el proceso termina."""

    @abstractmethod
    def hold(self) -> AbstractContextManager[None]: ...
