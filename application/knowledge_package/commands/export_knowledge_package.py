"""Caso de uso: exportar un NEXOM Knowledge Package v1.0.0, perfil CORE
(RAG-INC-01b, Alcance firmado §4 hito 01b y §5).

    export_knowledge_package(project_id, snapshot_id, tenant, output_dir)

- Trabaja SOLO sobre una instantánea publicada y elegida explícitamente;
  nunca sobre el proyecto vivo. La instantánea es de solo lectura.
- `tenant` es obligatorio (INC01-D4): ni se infiere ni hay valor por defecto.
- El registro `ProjectSnapshot` se carga una sola vez, como DTO inmutable.
- Las compuertas de contenido (huellas, identidades, referencias, colisiones
  portables) y la publicación atómica las aplica el adaptador
  (KnowledgePackageExporter)."""
from __future__ import annotations

import logging

from domain.knowledge_package.entities import KnowledgePackageExportResult, SnapshotDescriptor
from domain.knowledge_package.exceptions import MissingTenantError, SnapshotNotFoundError
from domain.knowledge_package.ports import KnowledgePackageExporter
from domain.release.ports import ProjectSnapshotRepository

logger = logging.getLogger(__name__)


class ExportKnowledgePackage:
    def __init__(self, snapshot_repository: ProjectSnapshotRepository, exporter: KnowledgePackageExporter):
        self._snapshots = snapshot_repository
        self._exporter = exporter

    def execute(self, project_id: str, snapshot_id: str, tenant: str, output_dir: str) -> KnowledgePackageExportResult:
        tenant_limpio = (tenant or "").strip()
        if not tenant_limpio:
            raise MissingTenantError()
        snapshot = self._snapshots.get(project_id, snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(project_id, snapshot_id)
        descriptor = SnapshotDescriptor.from_snapshot(snapshot)
        resultado = self._exporter.export(descriptor, tenant_limpio, output_dir)
        logger.info(
            "NEXOM Knowledge Package exportado: %s (proyecto %s, instantánea v%d, tenant %s) -> %s",
            resultado.package_id, project_id, snapshot.version, tenant_limpio, resultado.zip_path,
        )
        return resultado


def export_knowledge_package(
    use_case: ExportKnowledgePackage, project_id: str, snapshot_id: str, tenant: str, output_dir: str,
) -> KnowledgePackageExportResult:
    """Forma funcional con la firma prevista en el Alcance."""
    return use_case.execute(project_id, snapshot_id, tenant, output_dir)
