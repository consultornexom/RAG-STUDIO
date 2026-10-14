"""Excepciones del contexto Proyectos que la interfaz necesita
reconocer para ofrecer una salida al usuario, sin importar domain
directamente (ADR-001, sección 4) -- mismo criterio que
application.conversational.options. Ronda 88 (2026-10-02)."""
from __future__ import annotations

from domain.projects.exceptions import (
    DuplicateProjectError,
    ImportNameCollisionError,
    ImportResidueError,
    ProjectIdCollisionError,
)

__all__ = [
    "DuplicateProjectError",
    "ImportNameCollisionError",
    "ImportResidueError",
    "ProjectIdCollisionError",
]
