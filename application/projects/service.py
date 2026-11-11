"""Fachada de application para el contexto Proyectos.

Ensambla los casos de uso individuales para que ui y tests no tengan
que instanciar cada comando/consulta por separado. No contiene lógica
propia más allá de delegar.
"""
from __future__ import annotations

from typing import Optional

from domain.documents.ports import SourceRepository
from domain.projects.entities import Project
from domain.projects.packaging import IntegrityReport, PackageManifest
from domain.projects.ports import ConfigurationRepository, ImportLock, ProjectPackager, ProjectRepository

from .commands.archive_project import ArchiveProject
from .commands.backup_project import BackupProject
from .commands.change_project_status import ChangeProjectStatus
from .commands.clone_project import CloneProject
from .commands.create_project import CreateProject
from .commands.delete_project import DeleteProject
from .commands.export_project import ExportProject
from .commands.import_project import ImportProject
from .commands.update_project_details import UpdateProjectDetails
from .commands.update_project_name import UpdateProjectName
from .commands.update_quality_regression_threshold import UpdateQualityRegressionThreshold
from .commands.update_agent_reranking import UpdateAgentReranking
from .commands.validate_project_integrity import ValidateProjectIntegrity
from .queries.compare_projects import CompareProjects
from .queries.get_project import GetProject
from .queries.list_projects import ListProjects


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        configuration_repository: ConfigurationRepository,
        packager: ProjectPackager,
        source_repository: Optional[SourceRepository] = None,
        import_lock: Optional[ImportLock] = None,
    ):
        self._create = CreateProject(repository)
        self._clone = CloneProject(repository)
        self._archive = ArchiveProject(repository)
        self._export = ExportProject(repository, packager)
        self._import = ImportProject(repository, packager, import_lock=import_lock)
        self._validate_integrity = ValidateProjectIntegrity(packager)
        self._backup = BackupProject(repository, packager)
        self._get = GetProject(repository)
        self._list = ListProjects(repository)
        self._compare = CompareProjects(repository, configuration_repository)
        self._update_name = UpdateProjectName(repository)
        self._update_details = UpdateProjectDetails(repository)
        self._update_quality_regression_threshold = UpdateQualityRegressionThreshold(repository)
        self._update_agent_reranking = UpdateAgentReranking(repository)
        self._change_status = ChangeProjectStatus(repository)
        # source_repository es opcional solo para no romper a quien ya
        # instancia ProjectService sin él (p. ej. pruebas existentes que
        # no ejercitan borrado); delete_project() exige que sí se haya
        # pasado, ver más abajo.
        self._delete = DeleteProject(repository, source_repository) if source_repository is not None else None

    def create_project(self, name: str, **kwargs) -> Project:
        return self._create.execute(name, **kwargs)

    def clone_project(self, source_project_id: str, new_name: str) -> Project:
        return self._clone.execute(source_project_id, new_name)

    def archive_project(self, project_id: str) -> Project:
        return self._archive.execute(project_id)

    def update_project_name(self, project_id: str, new_name: str) -> Project:
        return self._update_name.execute(project_id, new_name)

    def update_project_details(self, project_id: str, **kwargs) -> Project:
        """Edita los siete campos descriptivos (Ronda 15, punto 48).
        kwargs acepta los mismos nombres que create_project(): cualquiera
        que se omita o se pase como None se deja sin cambios."""
        return self._update_details.execute(project_id, **kwargs)

    def update_quality_regression_threshold(self, project_id: str, threshold: Optional[float]) -> Project:
        """Ronda 53 (opción B' confirmada por el consultor): umbral de
        caída relativa de Recall@3/MRR que usa la compuerta de
        liberación "Regresión de recuperación". `None` vuelve a usar el
        valor por defecto de la instalación -- ver UpdateQualityRegressionThreshold."""
        return self._update_quality_regression_threshold.execute(project_id, threshold)

    def update_agent_reranking(self, project_id: str, enabled: Optional[bool]) -> Project:
        """Ronda 102 (C4): "Reranking en el agente" del proyecto. None =
        automático (predeterminado), True = activado, False = desactivado."""
        return self._update_agent_reranking.execute(project_id, enabled)

    def change_project_status(self, project_id: str, target_status: str) -> Project:
        """Mueve el estado de un proyecto (Ronda 15, punto 48). target_status
        es un string (p. ej. "en_configuracion"), nunca un ProjectStatus,
        para que ui/ no tenga que importar domain."""
        return self._change_status.execute(project_id, target_status)

    def get_allowed_next_statuses(self, project_id: str) -> list[str]:
        """Strings, no ProjectStatus: ui/ solo llama a application y no
        puede importar domain (ver docstring de ui/projects/panel.py)."""
        project = self._get.execute(project_id)
        return sorted(status.value for status in project.allowed_next_statuses())

    def delete_project(self, project_id: str) -> None:
        """Punto 13 (Ronda 3): borrado real, solo si el proyecto no tiene
        fuentes registradas -- ver DeleteProject/ProjectInUseError."""
        if self._delete is None:
            raise RuntimeError(
                "ProjectService no fue configurado con SourceRepository; no se puede eliminar proyectos."
            )
        self._delete.execute(project_id)

    def export_project(
        self, project_id: str, destination_path: str, include_documents: bool = True
    ) -> PackageManifest:
        return self._export.execute(project_id, destination_path, include_documents)

    def import_project(
        self, package_path: str, new_project_id: Optional[str] = None, new_name: Optional[str] = None,
        set_aside_residue: bool = False, identity_policy: object = None,
    ) -> Project:
        """Ronda 88: new_name (importar con otro nombre) y set_aside_residue
        (apartar restos de un intento anterior incompleto). RAG-INC-01a:
        `identity_policy` ("preserve" o "fork") es obligatoria -- ver
        application.projects.commands.import_project."""
        return self._import.execute(
            package_path, new_project_id=new_project_id, new_name=new_name, set_aside_residue=set_aside_residue,
            identity_policy=identity_policy,
        )

    def validate_integrity(self, package_path: str) -> IntegrityReport:
        return self._validate_integrity.execute(package_path)

    def backup_project(self, project_id: str, destination_path: str) -> PackageManifest:
        return self._backup.execute(project_id, destination_path)

    def get_project(self, project_id: str) -> Project:
        return self._get.execute(project_id)

    def list_projects(self, include_archived: bool = True) -> list[Project]:
        return self._list.execute(include_archived=include_archived)

    def compare_projects(self, project_id_a: str, project_id_b: str) -> dict:
        return self._compare.execute(project_id_a, project_id_b)
