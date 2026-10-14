"""Excepciones del contexto Proyectos que la interfaz necesita
reconocer para ofrecer una salida al usuario, sin importar domain
directamente (ADR-001, sección 4) -- mismo criterio que
application.conversational.options. Ronda 88 (2026-10-02)."""
from __future__ import annotations

from domain.projects.entities import IdentityPolicy
from domain.projects.exceptions import (
    DuplicateProjectError,
    ImportLockTimeoutError,
    ImportNameCollisionError,
    ImportResidueError,
    KnowledgeBaseIdentityCollisionError,
    ProjectIdCollisionError,
)

# RAG-INC-01a (decisión NEXOM D-1): valores de identity_policy que usa la UI.
IMPORT_POLICY_PRESERVE = IdentityPolicy.PRESERVE.value
IMPORT_POLICY_FORK = IdentityPolicy.FORK.value

__all__ = [
    "DuplicateProjectError",
    "IMPORT_POLICY_FORK",
    "IMPORT_POLICY_PRESERVE",
    "ImportLockTimeoutError",
    "ImportNameCollisionError",
    "ImportResidueError",
    "KnowledgeBaseIdentityCollisionError",
    "ProjectIdCollisionError",
]
