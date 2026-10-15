"""Resultado de la compuerta de conformidad NEXOM Knowledge Package
(RAG-INC-01c). Un paquete generado por RAG Studio solo es liberable con
status PASS."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConformanceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class ConformanceCategory(str, Enum):
    CONTRATO = "contrato"
    """El contrato vendorizado no es el firmado, o falta una dependencia."""
    SCHEMA = "schema"
    CHECKSUM = "checksum"
    CONTENT_DIGEST = "content_digest"
    IDS = "ids"
    UNICIDAD = "unicidad"
    REFERENCIA = "referencia"
    ESTRUCTURA = "estructura"
    CARDINALIDAD = "cardinalidad"
    PERFIL = "perfil"
    CAPACIDADES = "capacidades"
    ACEPTACION = "aceptacion"
    ZIP = "zip"
    OTRO = "otro"


@dataclass(frozen=True)
class ConformanceIssue:
    category: ConformanceCategory
    message: str
    origin: str
    """`validador_firmado` (validate_knowledge_package.py v1.0.0) o
    `rag_studio` (comprobación adicional, más estricta, de la compuerta)."""


@dataclass(frozen=True)
class ConformanceReport:
    status: ConformanceStatus
    contract_version: str
    checks_ok: int
    issues: tuple[ConformanceIssue, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.status == ConformanceStatus.PASS

    def by_category(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for issue in self.issues:
            conteo[issue.category.value] = conteo.get(issue.category.value, 0) + 1
        return conteo

    def summary(self, max_issues: int = 10) -> str:
        if self.passed:
            return f"PASS (contrato {self.contract_version}; {self.checks_ok} comprobaciones, 0 errores)"
        lineas = [f"FAIL (contrato {self.contract_version}; {len(self.issues)} error(es): {self.by_category()})"]
        lineas += [f"- [{i.category.value}] {i.message}" for i in self.issues[:max_issues]]
        if len(self.issues) > max_issues:
            lineas.append(f"- … y {len(self.issues) - max_issues} más")
        return "\n".join(lineas)
