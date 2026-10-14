"""Umbrales usados por las consultas de application/runtime (ADR-001,
sección 4: la UI y otros consumidores leen estas constantes en vez de
tener cada uno su propio número mágico)."""
from __future__ import annotations

REOPENING_ALERTAS_PROACTIVAS_MIN_TURNOS_30D: int = 50
"""Ronda 45 (RAG_STUDIO_Propuesta_Roadmap_RAG5_Pendientes.docx,
sección 9): condición 3 de "alertas proactivas" -- al menos 50 turnos
de conversation_log en los últimos 30 días naturales."""

REOPENING_APRENDIZAJE_MIN_ENTRADAS: int = 100
"""Ronda 45: condición 1 de "aprendizaje del retrieval, Opción 3" --
al menos 100 entradas totales en retrieval_feedback."""

REOPENING_APRENDIZAJE_MIN_FUENTES_DISTINTAS: int = 10
"""Ronda 45: condición 2 -- repartidas en al menos 10 source_id
distintos."""

REOPENING_APRENDIZAJE_MIN_DIAS_DE_USO: int = 30
"""Ronda 45: condición 3 -- acumuladas en un período de uso real de al
menos 30 días naturales."""


FAILED_ACTION_OPTION: str = "fallo"
"""Ronda 93: acción registrada para un turno que no pudo atenderse por un
error técnico (ver domain.runtime.entities.FAILED_ACTION) -- re-exportada
para la UI, que no importa domain directamente."""
