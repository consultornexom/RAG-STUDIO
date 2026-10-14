"""Pruebas de integración reales (SQLite vía Alembic) de los 4
repositorios del contexto Conversacional (Etapa 5)."""
from domain.conversational.entities import (
    ChannelingScheme, ConversationalVariable, GuardrailRule, Intent, IntentResolutionMode, RuleActionType,
    RuleCondition, RuleType,
)
from infrastructure.database.conversational_repositories import (
    SqlAlchemyChannelingSchemeRepository, SqlAlchemyConversationalVariableRepository,
    SqlAlchemyGuardrailRuleRepository, SqlAlchemyIntentRepository,
)
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_intent_round_trip_preserves_all_fields(tmp_path):
    repo = SqlAlchemyIntentRepository(_paths(tmp_path))
    intent = Intent(
        project_id="p1", name="Consultar requisitos", description="qué se necesita",
        positive_examples=["requisitos de ingreso"], negative_examples=["baja del programa"],
        priority=3, risk_level="alto", required_variables=["programa"], optional_variables=["plantel"],
        clarifying_questions={"programa": "¿Qué programa?"}, response_rule="responder con la lista completa",
        fallback_channeling_code="soporte-humano", resolution_mode=IntentResolutionMode.ESTRUCTURADO,
    )
    repo.save(intent)

    fetched = repo.get("p1", intent.id)
    assert fetched is not None
    assert fetched.name == "Consultar requisitos"
    assert fetched.positive_examples == ["requisitos de ingreso"]
    assert fetched.negative_examples == ["baja del programa"]
    assert fetched.priority == 3
    assert fetched.risk_level.value == "alto"
    assert fetched.required_variables == ["programa"]
    assert fetched.optional_variables == ["plantel"]
    assert fetched.clarifying_questions == {"programa": "¿Qué programa?"}
    assert fetched.fallback_channeling_code == "soporte-humano"
    assert fetched.active is True
    # Pista B.4 del ADR-003: el bug real que esto habría detectado --
    # IntentRecord/_record_to_intent no persistían/leían resolution_mode
    # en absoluto (solo se probaba a nivel de fake en memoria), así que
    # toda intención ESTRUCTURADO se leía de vuelta como SEMANTICO tras
    # un ciclo real de guardar/leer -- ver Ronda 28.
    assert fetched.resolution_mode == IntentResolutionMode.ESTRUCTURADO


def test_intent_defaults_to_semantic_resolution_mode_when_not_specified(tmp_path):
    repo = SqlAlchemyIntentRepository(_paths(tmp_path))
    intent = Intent(project_id="p1", name="Consultar requisitos")
    repo.save(intent)

    fetched = repo.get("p1", intent.id)
    assert fetched.resolution_mode == IntentResolutionMode.SEMANTICO


def test_intent_save_upserts_by_id(tmp_path):
    repo = SqlAlchemyIntentRepository(_paths(tmp_path))
    intent = Intent(project_id="p1", name="Consultar requisitos")
    repo.save(intent)
    updated = intent.model_copy(update={"active": False, "priority": 9})
    repo.save(updated)

    fetched = repo.get("p1", intent.id)
    assert fetched.active is False
    assert fetched.priority == 9
    assert len(repo.list_for_project("p1")) == 1


def test_intent_get_returns_none_for_wrong_project(tmp_path):
    repo = SqlAlchemyIntentRepository(_paths(tmp_path))
    intent = Intent(project_id="p1", name="Consultar requisitos")
    repo.save(intent)
    assert repo.get("p2", intent.id) is None


def test_conversational_variable_round_trip(tmp_path):
    repo = SqlAlchemyConversationalVariableRepository(_paths(tmp_path))
    variable = ConversationalVariable(
        project_id="p1", code="programa", label="Programa", metadata_field_id="f1",
        structured_column="plantel",
    )
    repo.save(variable)

    fetched = repo.get("p1", variable.id)
    assert fetched.code == "programa"
    assert fetched.metadata_field_id == "f1"
    assert fetched.structured_column == "plantel"  # Pista B.4 del ADR-003
    assert [v.code for v in repo.list_for_project("p1")] == ["programa"]


def test_guardrail_rule_round_trip_preserves_conditions(tmp_path):
    repo = SqlAlchemyGuardrailRuleRepository(_paths(tmp_path))
    rule = GuardrailRule(
        project_id="p1", name="Confianza baja", rule_type=RuleType.ACLARACION,
        conditions=[
            RuleCondition(field="confianza", operator="<", value="0.70"),
            RuleCondition(field="intencion", operator="=", value="consultar procedimiento"),
        ],
        action=RuleActionType.ACLARAR, priority=5,
    )
    repo.save(rule)

    fetched = repo.get("p1", rule.id)
    assert fetched is not None
    assert fetched.rule_type.value == "aclaracion"
    assert fetched.action.value == "aclarar"
    assert len(fetched.conditions) == 2
    assert fetched.conditions[0].field == "confianza"
    assert fetched.conditions[0].operator.value == "<"
    assert fetched.priority == 5


def test_guardrail_rule_list_orders_by_priority_descending(tmp_path):
    repo = SqlAlchemyGuardrailRuleRepository(_paths(tmp_path))
    repo.save(GuardrailRule(project_id="p1", name="baja", rule_type=RuleType.TONO, priority=1))
    repo.save(GuardrailRule(project_id="p1", name="alta", rule_type=RuleType.TONO, priority=9))
    names = [r.name for r in repo.list_for_project("p1")]
    assert names == ["alta", "baja"]


def test_channeling_scheme_round_trip_and_get_by_code(tmp_path):
    repo = SqlAlchemyChannelingSchemeRepository(_paths(tmp_path))
    scheme = ChannelingScheme(
        project_id="p1", code="soporte-humano", name="Soporte humano", reason="no hay certeza",
        target_area="mesa de ayuda", required_data=["nombre", "matrícula"], medium="ticket",
        user_message="Un asesor te contactará.",
    )
    repo.save(scheme)

    by_id = repo.get("p1", scheme.id)
    by_code = repo.get_by_code("p1", "soporte-humano")
    assert by_id is not None and by_code is not None
    assert by_id.id == by_code.id
    assert by_code.required_data == ["nombre", "matrícula"]
    assert by_code.medium.value == "ticket"


def test_channeling_scheme_get_by_code_returns_none_when_missing(tmp_path):
    repo = SqlAlchemyChannelingSchemeRepository(_paths(tmp_path))
    assert repo.get_by_code("p1", "no-existe") is None


def test_edit_channeling_scheme_from_ui_values_persists_in_sqlite(tmp_path):
    """Ronda 87 (2026-10-02, hallazgo real de usuario): la edición desde la
    interfaz fallaba con "'str' object has no attribute 'value'" al
    guardar en SQLite. Reproduce el caso real de la captura."""
    from application.conversational.commands.update_channeling_scheme import UpdateChannelingScheme
    from domain.conversational.entities import ChannelingMedium

    repo = SqlAlchemyChannelingSchemeRepository(_paths(tmp_path))
    scheme = ChannelingScheme(project_id="p1", code="canal_asesor_humano", name="Asesor", medium="correo")
    repo.save(scheme)

    UpdateChannelingScheme(repo).execute(
        "p1", scheme.id, "Canalización a asesor humano", reason="La persona pide un asesor.",
        condition="Solicitud de asesor humano", target_area="Atención a aspirantes", priority=90,
        medium="correo", required_data=[], allowed_data=["programa_academico"], forbidden_data=[],
        summary_template="Usuario solicita atención de un asesor humano.",
        user_message="Voy a canalizar tu solicitud con un asesor.", alternative_action="Información general.",
    )

    fetched = repo.get("p1", scheme.id)
    assert fetched.medium == ChannelingMedium.CORREO
    assert fetched.priority == 90
    assert fetched.condition == "Solicitud de asesor humano"
    assert fetched.allowed_data == ["programa_academico"]
