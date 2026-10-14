"""Pruebas unitarias de las entidades del contexto Liberación (Etapa 7)."""
from domain.release.entities import GateResult, ReleaseChecklist, ReleaseStatus


def test_release_status_has_the_eight_values_from_the_master_document():
    values = {status.value for status in ReleaseStatus}
    assert values == {
        "no_iniciada", "en_preparacion", "en_ejecucion", "en_revision",
        "aprobada", "rechazada", "bloqueada", "sustituida",
    }


def test_checklist_all_passed_true_when_every_gate_passes():
    checklist = ReleaseChecklist(gates=[
        GateResult(name="Metadatos", passed=True, reason="ok"),
        GateResult(name="Calidad", passed=True, reason="ok"),
    ])
    assert checklist.all_passed is True
    assert checklist.failed_gates == []


def test_checklist_all_passed_false_when_any_gate_fails():
    checklist = ReleaseChecklist(gates=[
        GateResult(name="Metadatos", passed=True, reason="ok"),
        GateResult(name="Calidad", passed=False, reason="sin casos de prueba"),
    ])
    assert checklist.all_passed is False
    assert [g.name for g in checklist.failed_gates] == ["Calidad"]


def test_checklist_all_passed_true_when_no_gates_evaluated():
    assert ReleaseChecklist(gates=[]).all_passed is True
