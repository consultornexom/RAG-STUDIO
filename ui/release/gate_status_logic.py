"""Lógica pura del aviso temprano de compuertas de Liberación (Etapa
7). Sin PySide6 -- se puede probar en cualquier entorno, incluso sin
las bibliotecas nativas de Qt (libEGL/libGL) que sí requiere
`ui/release/gate_status.py` (mismo criterio que
`ui/ingestion/search_highlighting.py`)."""
from __future__ import annotations

from typing import Optional

from domain.release.entities import GateResult, ReleaseChecklist


def find_gate(checklist: ReleaseChecklist, gate_name: str) -> Optional[GateResult]:
    return next((gate for gate in checklist.gates if gate.name == gate_name), None)


def gate_status_text(gate_name: str, gate: Optional[GateResult]) -> str:
    if gate is None:
        return f"Compuerta de Liberación ({gate_name}): no se pudo evaluar todavía."
    state = "cumplida" if gate.passed else "pendiente"
    return f"Compuerta de Liberación ({gate_name}): {state} -- {gate.reason}"
