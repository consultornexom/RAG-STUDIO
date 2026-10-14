"""Vocabularios que la UI necesita para construir formularios, sin
tener que importar domain directamente (ADR-001, sección 4)."""
from __future__ import annotations

from domain.quality.entities import TestCategory, TestSeverity

TEST_CATEGORY_OPTIONS: list[str] = [category.value for category in TestCategory]
TEST_SEVERITY_OPTIONS: list[str] = [severity.value for severity in TestSeverity]
EVALUATION_SCOPE_OPTIONS: list[str] = ["completa", "categoria", "individual"]

DEFAULT_QUALITY_REGRESSION_THRESHOLD: float = 0.15
"""Ronda 53 (Propuesta de evaluación continua reforzada, opción B'):
umbral de caída relativa de Recall@3/MRR usado por la compuerta de
liberación "Regresión de recuperación" cuando un proyecto no configuró
uno propio (Project.quality_regression_threshold es None) -- 15%
relativo, confirmado por el consultor tras la Ronda 52."""
