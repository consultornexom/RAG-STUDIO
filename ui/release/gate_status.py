"""Aviso temprano de compuertas de Liberación (Etapa 7), reutilizable
desde cualquier pestaña anterior (Metadatos, Ingesta, Diseño
conversacional, Calidad).

Alcance decidido en Etapa 7 (ver README, "Limitaciones conocidas"): las
compuertas se EVALÚAN solo al solicitar una liberación, no se
retrofita un bloqueo preventivo dentro de cada pestaña -- ese alcance
mayor (impedir una acción si la compuerta no se cumple) sigue fuera de
esta iteración. Lo que sí se agrega aquí es visibilidad temprana, sin
bloquear nada: cada pestaña relevante muestra, en una sola línea, si SU
compuerta ya se cumpliría hoy si se solicitara una liberación --así el
usuario no tiene que ir hasta Liberación y solicitar una evaluación
para enterarse de que, por ejemplo, todavía no hay ningún caso de
prueba en el banco. Es una lectura de solo consulta
(`ReleaseService.evaluate_gates`, ya existente desde Etapa 7): no
crea, no bloquea, no cambia ningún dato.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QWidget

from ui.release.gate_status_logic import find_gate, gate_status_text

__all__ = ["find_gate", "gate_status_text", "GateStatusLabel"]


class GateStatusLabel(QLabel):
    """Etiqueta de una sola línea (con salto de línea automático si no
    cabe) que refleja el estado de UNA compuerta de Liberación
    concreta. No es un widget bloqueante: solo se actualiza llamando a
    `refresh(release_service, project_id)`; si esa llamada falla (p.
    ej. el proyecto no tiene todavía nada configurado en otra etapa),
    se muestra un mensaje neutral en vez de propagar la excepción --
    esta etiqueta nunca debe impedir que el resto de la pestaña
    funcione."""

    def __init__(self, gate_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._gate_name = gate_name
        self.setWordWrap(True)
        self.clear_status()

    def clear_status(self) -> None:
        self.setText(f"Compuerta de Liberación ({self._gate_name}): sin proyecto activo.")

    def refresh(self, release_service, project_id: Optional[str]) -> None:
        if not project_id:
            self.clear_status()
            return
        try:
            checklist = release_service.evaluate_gates(project_id)
        except Exception:  # noqa: BLE001 - aviso de solo lectura, nunca debe tumbar la pestaña
            self.setText(f"Compuerta de Liberación ({self._gate_name}): no se pudo evaluar todavía.")
            return
        gate = find_gate(checklist, self._gate_name)
        self.setText(gate_status_text(self._gate_name, gate))
