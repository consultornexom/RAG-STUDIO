"""Puerto del exportador NEXOM Knowledge Package (RAG-INC-01b)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .conformance import ConformanceReport
from .entities import KnowledgePackageExportResult, SnapshotDescriptor


class KnowledgePackageExporter(ABC):
    @abstractmethod
    def export(self, snapshot: SnapshotDescriptor, tenant: str, output_dir: str) -> KnowledgePackageExportResult:
        """Genera el paquete CORE a partir del project.db de la instantánea
        (solo lectura) y lo publica de forma atómica en `output_dir`.
        Lanza un KnowledgePackageExportError ante cualquier compuerta fallida,
        sin dejar archivos finales."""
        ...


class KnowledgePackageConformanceValidator(ABC):
    """Compuerta de conformidad contractual (RAG-INC-01c)."""

    @abstractmethod
    def validate(self, package_path: str, content_digest_file: Optional[str] = None) -> ConformanceReport:
        """Valida un paquete (directorio o ZIP) contra el contrato vendorizado.
        Nunca lanza por un paquete inválido: devuelve FAIL con diagnóstico."""
        ...
