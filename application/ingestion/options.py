"""Vocabularios que la UI necesita para construir formularios, sin
tener que importar domain directamente (ADR-001, sección 4)."""
from __future__ import annotations

from domain.ingestion.entities import FragmentationStrategy

FRAGMENTATION_STRATEGY_OPTIONS: list[str] = [s.value for s in FragmentationStrategy]
