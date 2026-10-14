"""Dobles de prueba en memoria para los puertos de domain. Permiten
probar application sin tocar SQLite ni el sistema de archivos."""
from __future__ import annotations

from typing import Optional

from domain.projects.entities import ConfigurationEntry, IdentityPolicy, Project
from domain.projects.packaging import IntegrityReport, PackageManifest
from domain.projects.ports import ConfigurationRepository, ProjectPackager, ProjectRepository


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self):
        self._by_id: dict[str, Project] = {}

    def save(self, project: Project) -> None:
        self._by_id[project.id] = project

    def get(self, project_id: str) -> Optional[Project]:
        return self._by_id.get(project_id)

    def get_by_name(self, name: str) -> Optional[Project]:
        return next((p for p in self._by_id.values() if p.name == name), None)

    def list(self, include_archived: bool = True) -> list[Project]:
        return [p for p in self._by_id.values() if include_archived or not p.is_archived()]

    def delete(self, project_id: str) -> None:
        self._by_id.pop(project_id, None)


class InMemoryConfigurationRepository(ConfigurationRepository):
    def __init__(self):
        self._entries: list[ConfigurationEntry] = []

    def save(self, entry: ConfigurationEntry) -> None:
        self._entries.append(entry)

    def get_latest(self, project_id: str, key: str) -> Optional[ConfigurationEntry]:
        matches = [e for e in self._entries if e.project_id == project_id and e.key == key]
        return max(matches, key=lambda e: e.version, default=None)

    def list_for_project(self, project_id: str) -> list[ConfigurationEntry]:
        return [e for e in self._entries if e.project_id == project_id]


class FakeProjectPackager(ProjectPackager):
    """Registra las llamadas recibidas; no toca disco. Las pruebas de
    export/import reales contra el sistema de archivos viven en
    tests/integration, con el adaptador de verdad."""

    def __init__(self, integrity_is_valid: bool = True):
        self.export_calls: list[tuple] = []
        self.import_calls: list[str] = []
        self._integrity_is_valid = integrity_is_valid

    def export(self, project_id, destination_path, include_documents=True):
        self.export_calls.append((project_id, destination_path, include_documents))
        return PackageManifest(
            project_id=project_id, project_name="fake", includes_documents=include_documents,
        )

    # Ronda 88: id/nombre que "trae" el paquete falso y datos en disco
    # simulados, para probar las colisiones en ImportProject.
    manifest_project_id = "imported-id"
    manifest_project_name = "Proyecto importado"

    # RAG-INC-01a: knowledge_base_id que "trae" el paquete falso.
    manifest_knowledge_base_id = "kb-del-paquete"

    def import_project(self, package_path, new_project_id=None, new_name=None,
                       identity_policy=IdentityPolicy.PRESERVE):
        self.import_calls.append(package_path)
        self.import_policies = getattr(self, "import_policies", []) + [IdentityPolicy(identity_policy)]
        project_id = new_project_id or self.manifest_project_id
        self.on_disk.add(project_id)
        if IdentityPolicy(identity_policy) == IdentityPolicy.FORK:
            return Project(id=project_id, name=new_name or self.manifest_project_name)
        return Project(id=project_id, name=new_name or self.manifest_project_name,
                       knowledge_base_id=self.manifest_knowledge_base_id)

    def read_knowledge_base_id(self, package_path):
        return self.manifest_knowledge_base_id

    def inspect_package(self, package_path):
        return PackageManifest(
            project_id=self.manifest_project_id, project_name=self.manifest_project_name, includes_documents=True,
        )

    @property
    def on_disk(self) -> set:
        if not hasattr(self, "_on_disk"):
            self._on_disk: set = set()
        return self._on_disk

    def has_project_data(self, project_id):
        return project_id in self.on_disk

    def quarantine_project_data(self, project_id):
        self.on_disk.discard(project_id)
        return f"/residuos_importacion/{project_id}"

    def discard_project_data(self, project_id):
        self.on_disk.discard(project_id)

    def verify_integrity(self, package_path):
        return IntegrityReport(
            package_path=package_path, is_valid=self._integrity_is_valid, checked_files=1,
            error=None if self._integrity_is_valid else "forzado a inválido para la prueba",
        )

    def backup(self, project_id, destination_path):
        return self.export(project_id, destination_path, include_documents=True)
