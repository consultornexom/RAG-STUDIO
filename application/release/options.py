"""Vocabularios del contexto Liberación expuestos a la UI (ADR-001: la
UI nunca importa domain directamente)."""
from __future__ import annotations

from domain.release.entities import ReleaseStatus

RELEASE_STATUS_OPTIONS = [status.value for status in ReleaseStatus]
