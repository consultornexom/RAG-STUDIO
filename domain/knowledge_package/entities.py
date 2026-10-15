"""DTO inmutables de la exportación NEXOM Knowledge Package (RAG-INC-01b)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.release.entities import ProjectSnapshot

CONTRACT_SCHEMA_VERSION = "1.0.0"
"""`manifest.schema_version`: versión del FORMATO (contrato firmado v1.0.0)."""

PROFILE_CORE = "CORE"


@dataclass(frozen=True)
class SnapshotDescriptor:
    """Registro `ProjectSnapshot` (vive en el project.db del proyecto VIVO),
    cargado una sola vez al iniciar la exportación (Alcance firmado, hito
    01b: "como DTO inmutable"). Son metadatos descriptivos; el contenido se
    lee del project.db de `snapshot_dir`."""

    id: str
    project_id: str
    version: int
    snapshot_dir: str
    created_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: ProjectSnapshot) -> "SnapshotDescriptor":
        return cls(
            id=snapshot.id, project_id=snapshot.project_id, version=snapshot.version,
            snapshot_dir=snapshot.snapshot_dir, created_at=snapshot.created_at,
        )


@dataclass(frozen=True)
class KnowledgePackageExportResult:
    package_id: str
    knowledge_base_id: str
    snapshot_id: str
    tenant: str
    zip_path: str
    """Paquete publicado (ZIP)."""
    content_digest_path: str
    """Sidecar externo `<paquete>.content.sha256` (fuera del paquete)."""
    content_digest: str
    checksums_json_hash: str
    zip_sha256: str
    counts: dict[str, int] = field(default_factory=dict)
