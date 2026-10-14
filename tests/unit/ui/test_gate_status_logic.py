"""Pruebas unitarias de la lógica pura del aviso temprano de
compuertas de Liberación (Etapa 7 -> ítem 3). Sin PySide6 -- igual
criterio que test_search_highlighting.py."""
from domain.release.entities import GateResult, ReleaseChecklist
from ui.release.gate_status_logic import find_gate, gate_status_text


def _checklist(*gates: GateResult) -> ReleaseChecklist:
    return ReleaseChecklist(gates=list(gates))


def test_find_gate_returns_matching_gate_by_name():
    metadatos = GateResult(name="Metadatos", passed=True, reason="ok")
    calidad = GateResult(name="Calidad", passed=False, reason="sin casos")
    checklist = _checklist(metadatos, calidad)

    assert find_gate(checklist, "Calidad") is calidad
    assert find_gate(checklist, "Metadatos") is metadatos


def test_find_gate_returns_none_when_gate_not_present():
    checklist = _checklist(GateResult(name="Metadatos", passed=True, reason="ok"))

    assert find_gate(checklist, "Calidad") is None


def test_gate_status_text_when_gate_missing():
    text = gate_status_text("Calidad", None)

    assert text == "Compuerta de Liberación (Calidad): no se pudo evaluar todavía."


def test_gate_status_text_when_gate_passed():
    gate = GateResult(name="Metadatos", passed=True, reason="Esquema activo con 3 campo(s) definido(s).")

    text = gate_status_text("Metadatos", gate)

    assert text == (
        "Compuerta de Liberación (Metadatos): cumplida -- Esquema activo con 3 campo(s) definido(s)."
    )


def test_gate_status_text_when_gate_pending():
    gate = GateResult(
        name="Calidad", passed=False, reason="No hay ningún caso de prueba en el banco de pruebas.",
    )

    text = gate_status_text("Calidad", gate)

    assert text == (
        "Compuerta de Liberación (Calidad): pendiente -- No hay ningún caso de prueba en el banco de pruebas."
    )
