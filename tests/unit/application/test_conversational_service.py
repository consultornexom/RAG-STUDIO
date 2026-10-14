"""Pruebas unitarias de ConversationalService (fachada de application
para el contexto Conversacional, Etapa 5) -- CRUD de intenciones,
variables, guardrails y esquemas de canalización."""
import pytest

from application.conversational.service import ConversationalService
from domain.conversational.exceptions import (
    ConversationalVariableNotFoundError, GuardrailRuleNotFoundError, IntentNotFoundError,
)

from .fakes_conversational import (
    InMemoryChannelingSchemeRepository, InMemoryConversationalVariableRepository,
    InMemoryGuardrailRuleRepository, InMemoryIntentRepository,
)
from .fakes_metadata import InMemorySourceMetadataRepository
from .fakes_rag import FakeEmbeddingProvider, FakeVectorStore, InMemoryIndexInfoRepository
from .fakes_ingestion import InMemoryChunkRepository
from application.rag.service import RagService


def _make_service() -> ConversationalService:
    rag_service = RagService(
        InMemoryChunkRepository(), FakeEmbeddingProvider(), FakeVectorStore(), InMemoryIndexInfoRepository(),
    )
    return ConversationalService(
        InMemoryIntentRepository(), InMemoryConversationalVariableRepository(),
        InMemoryGuardrailRuleRepository(), InMemoryChannelingSchemeRepository(),
        InMemorySourceMetadataRepository(), rag_service,
    )


def test_create_and_list_intents():
    service = _make_service()
    service.create_intent("p1", "Consultar requisitos", required_variables=["programa"])
    intents = service.list_intents("p1")
    assert len(intents) == 1
    assert intents[0].name == "Consultar requisitos"
    assert intents[0].required_variables == ["programa"]
    assert intents[0].active is True


def test_set_intent_active_toggles_without_deleting():
    service = _make_service()
    intent = service.create_intent("p1", "Consultar requisitos")
    updated = service.set_intent_active("p1", intent.id, False)
    assert updated.active is False
    assert [i.id for i in service.list_intents("p1")] == [intent.id]


def test_update_intent_corrects_name_and_description():
    # Ronda 3 (punto 13 de Validacion_observaciones_RAG_STUDIO.md): antes
    # solo existía Activar/Desactivar para intenciones -- ni siquiera la
    # edición parcial que ya tenían campos de metadatos y catálogos.
    service = _make_service()
    intent = service.create_intent("p1", "Consulta requisitios", description="typo")  # typo intencional
    updated = service.update_intent("p1", intent.id, "Consultar requisitos", description="sin typo")
    assert updated.name == "Consultar requisitos"
    assert updated.description == "sin typo"
    assert service.list_intents("p1")[0].name == "Consultar requisitos"


def test_update_intent_missing_raises():
    service = _make_service()
    with pytest.raises(IntentNotFoundError):
        service.update_intent("p1", "no-existe", "Nuevo nombre")


# ---------- resolution_mode / structured_column (Pista B.4 del ADR-003) ----------

def test_create_intent_defaults_to_semantic_resolution_mode():
    service = _make_service()
    intent = service.create_intent("p1", "Consultar requisitos")
    assert intent.resolution_mode.value == "semantico"


def test_create_intent_accepts_estructurado_resolution_mode():
    service = _make_service()
    intent = service.create_intent("p1", "Consultar costos", resolution_mode="estructurado")
    assert intent.resolution_mode.value == "estructurado"


def test_update_intent_reclassifies_resolution_mode_without_touching_name_or_description():
    service = _make_service()
    intent = service.create_intent("p1", "Consultar costos", description="descripción original")
    updated = service.update_intent(
        "p1", intent.id, intent.name, resolution_mode="estructurado",
    )
    assert updated.resolution_mode.value == "estructurado"
    assert updated.description == "descripción original"


def test_update_intent_without_resolution_mode_preserves_the_existing_value():
    service = _make_service()
    intent = service.create_intent("p1", "Consultar costos", resolution_mode="estructurado")
    updated = service.update_intent("p1", intent.id, "Consultar costos (corregido)")
    assert updated.resolution_mode.value == "estructurado"


# ---------- edición completa de intenciones (ajuste funcional del 2026-09-03,
# hallazgo real de usuario: "debe dejar editar una intención ya que el manual
# así lo indica") ----------

def test_update_intent_edits_full_descriptive_fields():
    service = _make_service()
    intent = service.create_intent(
        "p1", "Consultar requisitos", positive_examples=["¿qué necesito?"],
        negative_examples=["hola"], priority=10, risk_level="bajo",
        required_variables=["programa"], optional_variables=[],
        clarifying_questions={"programa": "¿qué programa?"}, response_rule="responder con requisitos",
        fallback_channeling_code=None,
    )
    updated = service.update_intent(
        "p1", intent.id, intent.name,
        positive_examples=["¿qué necesito?", "requisitos de ingreso"],
        negative_examples=["hola", "adiós"],
        priority=80, risk_level="alto",
        required_variables=["programa", "plantel"], optional_variables=["periodo"],
        clarifying_questions={"programa": "¿qué programa?", "plantel": "¿qué plantel?"},
        response_rule="responder citando la fuente oficial",
        fallback_channeling_code="soporte-humano",
    )
    assert updated.id == intent.id  # conserva su identificador
    assert updated.positive_examples == ["¿qué necesito?", "requisitos de ingreso"]
    assert updated.negative_examples == ["hola", "adiós"]
    assert updated.priority == 80
    assert updated.risk_level.value == "alto"
    assert updated.required_variables == ["programa", "plantel"]
    assert updated.optional_variables == ["periodo"]
    assert updated.clarifying_questions == {"programa": "¿qué programa?", "plantel": "¿qué plantel?"}
    assert updated.response_rule == "responder citando la fuente oficial"
    assert updated.fallback_channeling_code == "soporte-humano"


def test_update_intent_preserves_active_state_when_editing_other_fields():
    # Criterio de aceptación explícito del ajuste funcional: "La
    # intención conserva su estado activo/inactivo."
    service = _make_service()
    intent = service.create_intent("p1", "Consultar requisitos")
    service.set_intent_active("p1", intent.id, False)
    updated = service.update_intent("p1", intent.id, intent.name, priority=50)
    assert updated.active is False


def test_update_intent_can_clear_a_previously_set_fallback_channeling_code():
    # El diálogo de edición manda "" (nunca None) cuando la persona
    # borra el campo -- ver _EditIntentDialog.values() y el docstring
    # de UpdateIntent sobre el doble uso de None en este campo puntual.
    service = _make_service()
    intent = service.create_intent("p1", "Consultar costos", fallback_channeling_code="soporte-humano")
    updated = service.update_intent("p1", intent.id, intent.name, fallback_channeling_code="")
    assert updated.fallback_channeling_code is None


# ---------- eliminación de intenciones (ajuste funcional del 2026-09-04,
# hallazgo real de usuario: "en Guardrails sí permite tanto editar como
# eliminar y eso ayuda mucho... valide si en esta sección [Intenciones] es
# conveniente integrar la funcionalidad de Eliminar intención") ----------

def test_delete_intent_removes_it_from_the_project():
    service = _make_service()
    intent = service.create_intent("p1", "Intención a borrar")
    otra = service.create_intent("p1", "Otra intención")
    service.delete_intent("p1", intent.id)
    remaining = service.list_intents("p1")
    assert [i.id for i in remaining] == [otra.id]


def test_delete_intent_missing_raises():
    service = _make_service()
    with pytest.raises(IntentNotFoundError):
        service.delete_intent("p1", "no-existe")


def test_create_variable_accepts_an_optional_structured_column():
    service = _make_service()
    service.create_variable("p1", "plantel", "Plantel", structured_column="plantel")
    assert service.list_variables("p1")[0].structured_column == "plantel"


# ---------- find_rules_referencing_intent (Ronda 4: riesgo descubierto tras update_intent) ----------

def test_find_rules_referencing_intent_detects_condition_by_name():
    service = _make_service()
    service.create_intent("p1", "Consultar requisitos")
    service.create_guardrail_rule(
        "p1", "Confirmar requisitos", "elegibilidad",
        conditions=[{"field": "intencion", "operator": "=", "value": "Consultar requisitos"}],
    )
    service.create_guardrail_rule("p1", "Otra regla sin relación", "tono")

    affected = service.find_rules_referencing_intent("p1", "Consultar requisitos")
    assert [r.name for r in affected] == ["Confirmar requisitos"]


def test_find_rules_referencing_intent_is_case_and_space_insensitive():
    # Misma normalización que evaluate_condition (ver rule_evaluation.py)
    service = _make_service()
    service.create_guardrail_rule(
        "p1", "Regla", "elegibilidad",
        conditions=[{"field": "intencion", "operator": "=", "value": "  Consultar Requisitos  "}],
    )
    affected = service.find_rules_referencing_intent("p1", "consultar requisitos")
    assert len(affected) == 1


def test_find_rules_referencing_intent_returns_empty_when_no_match():
    service = _make_service()
    service.create_guardrail_rule(
        "p1", "Regla", "elegibilidad",
        conditions=[{"field": "intencion", "operator": "=", "value": "Otra intención"}],
    )
    assert service.find_rules_referencing_intent("p1", "Consultar requisitos") == []


def test_create_and_list_variables():
    service = _make_service()
    service.create_variable("p1", "programa", "Programa", metadata_field_id="f1")
    variables = service.list_variables("p1")
    assert len(variables) == 1
    assert variables[0].code == "programa"
    assert variables[0].metadata_field_id == "f1"


def test_update_variable_corrects_label_and_description():
    service = _make_service()
    variable = service.create_variable("p1", "programa", "Prograam", description="typo")
    updated = service.update_variable("p1", variable.id, "Programa", description="sin typo")
    assert updated.label == "Programa"
    assert updated.description == "sin typo"
    assert updated.code == "programa"  # code no es editable, ver UpdateConversationalVariable


def test_update_variable_missing_raises():
    service = _make_service()
    with pytest.raises(ConversationalVariableNotFoundError):
        service.update_variable("p1", "no-existe", "Nueva etiqueta")


def test_create_and_list_guardrail_rules_with_dict_conditions_from_ui():
    service = _make_service()
    # La UI nunca importa domain (ADR-001) -- pasa condiciones como
    # dicts (ver ui.conversational.parsing.parse_conditions).
    service.create_guardrail_rule(
        "p1", "Confianza baja", "aclaracion",
        conditions=[{"field": "confianza", "operator": "<", "value": "0.70"}],
        action="aclarar",
    )
    rules = service.list_guardrail_rules("p1")
    assert len(rules) == 1
    assert rules[0].conditions[0].field == "confianza"
    assert rules[0].action.value == "aclarar"


def test_update_channeling_scheme_edits_full_descriptive_fields():
    # Ronda 4 (punto 1): antes Canalización solo tenía Crear +
    # Activar/Desactivar -- el único de los cuatro catálogos de
    # Conversacional sin edición básica.
    service = _make_service()
    scheme = service.create_channeling_scheme(
        "p1", "CANAL-1", "Canalizar a control escolar", reason="motivo viejo",
    )
    updated = service.update_channeling_scheme(
        "p1", scheme.id, "Canalizar a servicios escolares", reason="motivo corregido",
        target_area="Servicios Escolares", priority=5,
    )
    assert updated.code == "CANAL-1"  # code no es editable
    assert updated.name == "Canalizar a servicios escolares"
    assert updated.reason == "motivo corregido"
    assert updated.target_area == "Servicios Escolares"
    assert updated.priority == 5


def test_update_channeling_scheme_missing_raises():
    from domain.conversational.exceptions import ChannelingSchemeNotFoundError

    service = _make_service()
    with pytest.raises(ChannelingSchemeNotFoundError):
        service.update_channeling_scheme("p1", "no-existe", "Nuevo nombre")


def test_set_guardrail_rule_active_toggles():
    service = _make_service()
    rule = service.create_guardrail_rule("p1", "regla", "aclaracion")
    updated = service.set_guardrail_rule_active("p1", rule.id, False)
    assert updated.active is False


def test_update_guardrail_rule_corrects_name():
    service = _make_service()
    rule = service.create_guardrail_rule("p1", "Confinza baja", "aclaracion")  # typo intencional
    updated = service.update_guardrail_rule("p1", rule.id, "Confianza baja")
    assert updated.name == "Confianza baja"


def test_update_guardrail_rule_missing_raises():
    service = _make_service()
    with pytest.raises(GuardrailRuleNotFoundError):
        service.update_guardrail_rule("p1", "no-existe", "Nuevo nombre")


# ---------- edición y eliminación completa de guardrails (ajuste funcional del
# 2026-09-03, hallazgo real de usuario: el manual documentaba "eliminar y
# crear nuevamente" pero la interfaz no tenía ningún "Eliminar") ----------

def test_update_guardrail_rule_edits_full_configuration_fields():
    service = _make_service()
    rule = service.create_guardrail_rule(
        "p1", "Confianza baja", "aclaracion",
        conditions=[{"field": "confianza", "operator": "<", "value": "0.70"}],
        action="aclarar", priority=10,
    )
    updated = service.update_guardrail_rule(
        "p1", rule.id, "Confianza muy baja", rule_type="abstencion",
        conditions=[{"field": "confianza", "operator": "<", "value": "0.50"}],
        action="abstenerse", priority=90,
    )
    assert updated.id == rule.id  # conserva su identificador
    assert updated.name == "Confianza muy baja"
    assert updated.rule_type.value == "abstencion"
    assert updated.action.value == "abstenerse"
    assert updated.priority == 90
    assert len(updated.conditions) == 1
    assert updated.conditions[0].field == "confianza"
    assert updated.conditions[0].value == "0.50"


def test_update_guardrail_rule_without_extra_fields_only_changes_name():
    # Llamada parcial (como la que hacía la interfaz antes de este
    # ajuste) sigue funcionando -- rule_type/conditions/action/priority
    # quedan sin tocar si no se pasan.
    service = _make_service()
    rule = service.create_guardrail_rule("p1", "Confinza baja", "aclaracion", priority=25)
    updated = service.update_guardrail_rule("p1", rule.id, "Confianza baja")
    assert updated.name == "Confianza baja"
    assert updated.rule_type.value == "aclaracion"
    assert updated.priority == 25


def test_update_guardrail_rule_preserves_active_state_when_editing_other_fields():
    service = _make_service()
    rule = service.create_guardrail_rule("p1", "Confianza baja", "aclaracion")
    service.set_guardrail_rule_active("p1", rule.id, False)
    updated = service.update_guardrail_rule("p1", rule.id, rule.name, priority=99)
    assert updated.active is False


def test_delete_guardrail_rule_removes_it_from_the_project():
    # Hallazgo real de usuario (ver bitácora): "lo resolví temporalmente
    # desactivando la regla pero el manual indica que se puede eliminar
    # y crear nuevamente pero la interfaz no tiene la opción para
    # elimina[r]."
    service = _make_service()
    rule = service.create_guardrail_rule("p1", "Regla a borrar", "tono")
    otra = service.create_guardrail_rule("p1", "Otra regla", "formato")
    service.delete_guardrail_rule("p1", rule.id)
    remaining = service.list_guardrail_rules("p1")
    assert [r.id for r in remaining] == [otra.id]


def test_delete_guardrail_rule_missing_raises():
    service = _make_service()
    with pytest.raises(GuardrailRuleNotFoundError):
        service.delete_guardrail_rule("p1", "no-existe")


def test_create_and_list_channeling_schemes():
    service = _make_service()
    service.create_channeling_scheme("p1", "soporte-humano", "Soporte humano", medium="ticket")
    schemes = service.list_channeling_schemes("p1")
    assert len(schemes) == 1
    assert schemes[0].code == "soporte-humano"
    assert schemes[0].medium.value == "ticket"


def test_set_channeling_scheme_active_toggles():
    service = _make_service()
    scheme = service.create_channeling_scheme("p1", "soporte-humano", "Soporte humano")
    updated = service.set_channeling_scheme_active("p1", scheme.id, False)
    assert updated.active is False


# ---------- Ronda 87 (2026-10-02, hallazgo real de usuario: "Al intentar
# modificar una canalización no permite guardarlo" -- "'str' object has no
# attribute 'value'") ----------

def test_update_channeling_scheme_converts_medium_text_from_the_ui_to_enum():
    from domain.conversational.entities import ChannelingMedium

    service = _make_service()
    scheme = service.create_channeling_scheme("p1", "canal_asesor_humano", "Asesor", medium="correo")
    # Exactamente lo que manda _EditChannelingSchemeDialog.values(): todo texto.
    updated = service.update_channeling_scheme(
        "p1", scheme.id, "Canalización a asesor humano", reason="La persona pide un asesor.",
        condition="Solicitud de asesor humano", target_area="Atención a aspirantes", priority=90,
        medium="correo", required_data=[], allowed_data=["programa_academico"], forbidden_data=[],
        summary_template="Usuario solicita atención", user_message="Voy a canalizar tu solicitud",
        alternative_action="Información general.",
    )
    assert isinstance(updated.medium, ChannelingMedium)
    assert updated.medium.value == "correo"
    assert updated.condition == "Solicitud de asesor humano"


def test_update_channeling_scheme_rejects_unknown_medium():
    from pydantic import ValidationError

    service = _make_service()
    scheme = service.create_channeling_scheme("p1", "c1", "Asesor")
    with pytest.raises(ValidationError):
        service.update_channeling_scheme("p1", scheme.id, "Asesor", medium="fax")


def test_create_channeling_scheme_duplicate_code_gives_clear_error():
    from domain.conversational.exceptions import DuplicateConversationalCodeError

    service = _make_service()
    service.create_channeling_scheme("p1", "canal_asesor_humano", "Asesor")
    with pytest.raises(DuplicateConversationalCodeError, match="canal_asesor_humano"):
        service.create_channeling_scheme("p1", "canal_asesor_humano", "Otro")


def test_create_conversational_variable_duplicate_code_gives_clear_error():
    from domain.conversational.exceptions import DuplicateConversationalCodeError

    service = _make_service()
    service.create_variable("p1", "plantel", "Plantel")
    with pytest.raises(DuplicateConversationalCodeError, match="plantel"):
        service.create_variable("p1", "plantel", "Otro plantel")
