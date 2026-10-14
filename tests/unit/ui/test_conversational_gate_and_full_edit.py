"""Ajuste funcional del 2026-09-03 (tres reportes reales de usuario,
ver bitácora):

1. La Compuerta de Liberación (Diseño conversacional) no se actualizaba
   de inmediato tras crear una intención, crear una regla de guardrail,
   o activar/desactivar una regla -- solo se veía correcta después de
   cerrar y volver a abrir RAG STUDIO. Corregido agregando el mismo
   refresco (`self._gate_status_label.refresh(...)`) que ya existía,
   de forma asimétrica, solo para activar/desactivar una intención.
2. Guardrails no tenía ninguna opción "Eliminar" pese a que el Manual
   del Usuario documentaba "eliminar y crear nuevamente" como la vía
   para cambiar tipo, condiciones, acción o prioridad de una regla.
3. Intenciones solo permitía editar nombre/descripción/vía de
   resolución -- el resto de la configuración (ejemplos, prioridad,
   riesgo, datos mínimos/opcionales, preguntas aclaratorias, regla de
   respuesta, canalización alternativa) quedaba bloqueado.

Mismo criterio de omisión automática sin Qt que el resto de
tests/unit/ui/ -- no ejecutable en este sandbox de consultoría por la
carencia de libEGL.so.1 ya documentada en rondas anteriores."""
import os

import pytest

try:
    import PySide6.QtWidgets  # noqa: F401
except ImportError as exc:
    pytest.skip(
        f"Qt no disponible en este entorno ({exc}); se omite la prueba de ui/conversational/panel.py.",
        allow_module_level=True,
    )

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import ui.conversational.panel as conversational_panel_module  # noqa: E402
from ui.conversational.panel import (  # noqa: E402
    ConversationalPanel, _EditGuardrailRuleDialog, _EditIntentDialog,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _make_panel_with_project(app_context, qapp) -> tuple[ConversationalPanel, str]:
    project = app_context.project_service.create_project("Proyecto de prueba")
    panel = ConversationalPanel(app_context)
    panel.set_active_project(project.id)
    return panel, project.id


# ---------- Fix 1: compuerta reactiva ----------

def test_creating_an_active_intent_refreshes_the_gate_immediately(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    # Guardrail activo ya presente -- falta únicamente una intención
    # activa para que la compuerta se cumpla.
    app_context.conversational_service.create_guardrail_rule(project_id, "Regla", "tono")
    panel._gate_status_label.refresh(app_context.release_service, project_id)
    assert "pendiente" in panel._gate_status_label.text()

    panel._intent_name.setText("Consultar requisitos de ingreso")
    panel._on_create_intent()

    assert "cumplida" in panel._gate_status_label.text()


def test_creating_an_active_guardrail_rule_refreshes_the_gate_immediately(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    app_context.conversational_service.create_intent(project_id, "Consultar requisitos")
    panel._gate_status_label.refresh(app_context.release_service, project_id)
    assert "pendiente" in panel._gate_status_label.text()

    panel._rule_name.setText("Abstenerse con baja confianza")
    panel._on_create_rule()

    assert "cumplida" in panel._gate_status_label.text()


def test_toggling_a_guardrail_rule_inactive_refreshes_the_gate_immediately(qapp, app_context):
    # Este es el hallazgo reportado literalmente: activar/desactivar una
    # intención sí refrescaba la compuerta; el mismo cambio en un
    # guardrail no.
    panel, project_id = _make_panel_with_project(app_context, qapp)
    app_context.conversational_service.create_intent(project_id, "Consultar requisitos")
    app_context.conversational_service.create_guardrail_rule(project_id, "Regla", "tono")
    panel._gate_status_label.refresh(app_context.release_service, project_id)
    assert "cumplida" in panel._gate_status_label.text()

    panel._refresh_rules()
    panel._rule_list.setCurrentRow(0)
    panel._on_toggle_rule()

    assert "pendiente" in panel._gate_status_label.text()


# ---------- Fix 2: guardrails -- edición completa y Eliminar ----------

def test_edit_guardrail_rule_dialog_prefills_current_values(qapp, app_context):
    _panel, project_id = _make_panel_with_project(app_context, qapp)
    rule = app_context.conversational_service.create_guardrail_rule(
        project_id, "Confianza baja", "aclaracion",
        conditions=[{"field": "confianza", "operator": "<", "value": "0.70"}],
        action="aclarar", priority=40,
    )
    dialog = _EditGuardrailRuleDialog(rule)
    assert dialog._name.text() == "Confianza baja"
    assert dialog._rule_type.currentText() == "aclaracion"
    assert dialog._action.currentText() == "aclarar"
    assert dialog._priority.value() == 40
    assert "confianza < 0.70" in dialog._conditions.toPlainText()


def test_edit_guardrail_rule_dialog_values_round_trip_into_update_call(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    rule = app_context.conversational_service.create_guardrail_rule(project_id, "Regla", "tono", priority=5)
    dialog = _EditGuardrailRuleDialog(rule)
    dialog._name.setText("Regla corregida")
    dialog._priority.setValue(70)
    values = dialog.values()
    updated = app_context.conversational_service.update_guardrail_rule(project_id, rule.id, **values)
    assert updated.name == "Regla corregida"
    assert updated.priority == 70
    panel._refresh_rules()  # no debe lanzar


def test_delete_rule_button_removes_the_selected_rule_and_refreshes_the_gate(qapp, app_context, monkeypatch):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    app_context.conversational_service.create_intent(project_id, "Consultar requisitos")
    app_context.conversational_service.create_guardrail_rule(project_id, "Única regla", "tono")
    panel._refresh_rules()
    panel._gate_status_label.refresh(app_context.release_service, project_id)
    assert "cumplida" in panel._gate_status_label.text()

    monkeypatch.setattr(
        conversational_panel_module.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    panel._rule_list.setCurrentRow(0)
    panel._on_delete_rule()

    assert app_context.conversational_service.list_guardrail_rules(project_id) == []
    # Sin ninguna regla, ya no puede haber "al menos un guardrail
    # activo" -- la compuerta debe volver a pendiente de inmediato.
    assert "pendiente" in panel._gate_status_label.text()


# ---------- Fix 3: intenciones -- edición completa ----------

def test_edit_intent_dialog_prefills_current_values(qapp, app_context):
    _panel, project_id = _make_panel_with_project(app_context, qapp)
    intent = app_context.conversational_service.create_intent(
        project_id, "Consultar requisitos", description="descripción original",
        positive_examples=["¿qué necesito?"], negative_examples=["hola"],
        priority=20, risk_level="medio", required_variables=["programa"],
        clarifying_questions={"programa": "¿qué programa?"}, response_rule="responder con requisitos",
        fallback_channeling_code="soporte-humano",
    )
    dialog = _EditIntentDialog(intent)
    assert dialog._name.text() == "Consultar requisitos"
    assert dialog._description.text() == "descripción original"
    assert dialog._positive.toPlainText() == "¿qué necesito?"
    assert dialog._negative.toPlainText() == "hola"
    assert dialog._priority.value() == 20
    assert dialog._risk.currentText() == "medio"
    assert dialog._required.text() == "programa"
    assert "programa: ¿qué programa?" in dialog._questions.toPlainText()
    assert dialog._response_rule.text() == "responder con requisitos"
    assert dialog._fallback.text() == "soporte-humano"


def test_edit_intent_dialog_values_round_trip_into_update_call(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    intent = app_context.conversational_service.create_intent(project_id, "Consultar requisitos", priority=10)
    dialog = _EditIntentDialog(intent)
    dialog._priority.setValue(95)
    dialog._risk.setCurrentText("alto")
    dialog._required.setText("programa, plantel")
    values = dialog.values()
    updated = app_context.conversational_service.update_intent(project_id, intent.id, **values)
    assert updated.priority == 95
    assert updated.risk_level.value == "alto"
    assert updated.required_variables == ["programa", "plantel"]
    panel._refresh_intents()  # no debe lanzar


def test_edit_intent_preserves_identifier_and_active_state_through_the_panel_handler(qapp, app_context):
    panel, project_id = _make_panel_with_project(app_context, qapp)
    intent = app_context.conversational_service.create_intent(project_id, "Consultar requisitos")
    app_context.conversational_service.set_intent_active(project_id, intent.id, False)
    panel._refresh_intents()

    panel._intent_list.setCurrentRow(0)
    # Simula lo que hace _on_edit_intent tras aceptar el diálogo, sin
    # abrir el modal (QDialog.exec() bloquea el hilo de pruebas):
    # llama directamente al servicio como lo haría el diálogo aceptado.
    updated = app_context.conversational_service.update_intent(
        project_id, intent.id, intent.name, priority=30,
    )
    assert updated.id == intent.id
    assert updated.active is False


def test_delete_intent_button_removes_the_selected_intent_and_refreshes_the_gate(qapp, app_context, monkeypatch):
    # Ajuste funcional del 2026-09-04 (hallazgo real de usuario, ver
    # bitácora): mismo patrón que test_delete_rule_button_removes_the_
    # selected_rule_and_refreshes_the_gate.
    panel, project_id = _make_panel_with_project(app_context, qapp)
    app_context.conversational_service.create_guardrail_rule(project_id, "Regla", "tono")
    app_context.conversational_service.create_intent(project_id, "Única intención")
    panel._refresh_intents()
    panel._gate_status_label.refresh(app_context.release_service, project_id)
    assert "cumplida" in panel._gate_status_label.text()

    monkeypatch.setattr(
        conversational_panel_module.QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    panel._intent_list.setCurrentRow(0)
    panel._on_delete_intent()

    assert app_context.conversational_service.list_intents(project_id) == []
    # Sin ninguna intención, ya no puede haber "al menos una intención
    # activa" -- la compuerta debe volver a pendiente de inmediato.
    assert "pendiente" in panel._gate_status_label.text()


def test_delete_intent_warns_about_guardrail_rules_referencing_its_name(qapp, app_context, monkeypatch):
    # Mismo aviso ya usado al renombrar (Ronda 4) -- ver
    # find_rules_referencing_intent. Se confirma que el aviso aparece
    # (QMessageBox.warning) antes de la confirmación de borrado
    # (QMessageBox.question), contando cuántas veces se llama a cada
    # una en vez de solo simular "Yes" para ambas.
    panel, project_id = _make_panel_with_project(app_context, qapp)
    app_context.conversational_service.create_intent(project_id, "Consultar requisitos")
    app_context.conversational_service.create_guardrail_rule(
        project_id, "Confirmar requisitos", "elegibilidad",
        conditions=[{"field": "intencion", "operator": "=", "value": "Consultar requisitos"}],
    )
    panel._refresh_intents()

    warning_calls = []
    question_calls = []
    monkeypatch.setattr(
        conversational_panel_module.QMessageBox, "warning",
        staticmethod(lambda *a, **k: warning_calls.append(a) or QMessageBox.Yes),
    )
    monkeypatch.setattr(
        conversational_panel_module.QMessageBox, "question",
        staticmethod(lambda *a, **k: question_calls.append(a) or QMessageBox.Yes),
    )
    panel._intent_list.setCurrentRow(0)
    panel._on_delete_intent()

    assert len(warning_calls) == 1
    assert "Confirmar requisitos" in warning_calls[0][2]
    assert len(question_calls) == 1
    assert app_context.conversational_service.list_intents(project_id) == []
