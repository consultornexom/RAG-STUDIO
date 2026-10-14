"""Objetos de valor del paquete portable .agentproj (ADR-001, sección 8).

Puramente descriptivos: no saben comprimir ni escribir en disco (eso es
infrastructure/filesystem). El dominio solo define la forma del dato.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UnsafeRelativePathError(ValueError):
    """relative_path no es una ruta relativa segura (auditoría Ronda
    46, hallazgo crítico -- Zip Slip): un paquete .agentproj fabricado
    a mano podía declarar una entrada con "../" o una ruta absoluta y
    verify_integrity() la aceptaba igual, porque solo comprobaba que
    los hashes fueran autoconsistentes, nunca que la ruta fuera segura.
    Este validador rechaza esa entrada en el momento en que se
    construye el objeto de dominio -- antes de que
    infrastructure/filesystem/packager.py pueda siquiera considerar
    escribirla en disco."""


class FileEntry(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int

    @field_validator("relative_path")
    @classmethod
    def _relative_path_debe_ser_segura(cls, v: str) -> str:
        """export() (infrastructure/filesystem/packager.py) solo
        produce rutas relativas reales, con separador "/", vía
        `path.relative_to(project_dir).as_posix()" -- nunca ".." ni
        una ruta absoluta. Cualquier entrada que no cumpla esa misma
        forma no puede venir de una exportación legítima de RAG
        STUDIO, así que se rechaza aquí, sin excepción."""
        if not v or not v.strip():
            raise UnsafeRelativePathError("relative_path no puede estar vacío.")
        if "\\" in v:
            raise UnsafeRelativePathError(
                f"relative_path {v!r} usa '\\\\' -- solo se acepta '/' como separador."
            )
        if v.startswith("/") or v.startswith("~"):
            raise UnsafeRelativePathError(f"relative_path {v!r} no puede ser una ruta absoluta.")
        if len(v) >= 2 and v[1] == ":":  # unidad de Windows, p. ej. "C:/..."
            raise UnsafeRelativePathError(f"relative_path {v!r} no puede ser una ruta absoluta.")
        if any(segment == ".." for segment in v.split("/")):
            raise UnsafeRelativePathError(
                f"relative_path {v!r} no puede contener un segmento '..' (path traversal)."
            )
        return v


class PackageManifest(BaseModel):
    project_id: str
    project_name: str
    format_version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    includes_documents: bool
    files: list[FileEntry] = Field(default_factory=list)
    manifest_sha256: Optional[str] = None
    """Hash del propio manifiesto (sin este campo) para verificar integridad."""


class IntegrityReport(BaseModel):
    package_path: str
    is_valid: bool
    checked_files: int
    mismatched_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    error: Optional[str] = None
