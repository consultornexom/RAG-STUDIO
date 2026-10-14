"""Pruebas unitarias de evaluate_condition/evaluate_rule/select_firing_action
(Etapa 5, guardrails)."""
from domain.conversational.entities import GuardrailRule, RuleActionType, RuleCondition, RuleType
from domain.conversational.rule_evaluation import evaluate_condition, evaluate_rule, select_firing_action


def _rule(**kwargs) -> GuardrailRule:
    kwargs.setdefault("project_id", "p1")
    kwargs.setdefault("name", "regla")
    kwargs.setdefault("rule_type", RuleType.ACLARACION)
    return GuardrailRule(**kwargs)


def test_evaluate_condition_numeric_menor():
    condition = RuleCondition(field="confianza", operator="<", value="0.70")
    assert evaluate_condition(condition, {"confianza": "0.50"}) is True
    assert evaluate_condition(condition, {"confianza": "0.90"}) is False


def test_evaluate_condition_igual_case_insensitive_text():
    condition = RuleCondition(field="intencion", operator="=", value="Consultar Requisitos")
    assert evaluate_condition(condition, {"intencion": "consultar requisitos"}) is True
    assert evaluate_condition(condition, {"intencion": "otra intención"}) is False


def test_evaluate_condition_contiene():
    condition = RuleCondition(field="intencion", operator="contiene", value="requisitos")
    assert evaluate_condition(condition, {"intencion": "consultar requisitos de ingreso"}) is True
    assert evaluate_condition(condition, {"intencion": "consultar horarios"}) is False


def test_evaluate_condition_unknown_field_is_false():
    condition = RuleCondition(field="campo_inexistente", operator="=", value="x")
    assert evaluate_condition(condition, {"otro_campo": "x"}) is False


def test_evaluate_condition_relational_operator_with_non_numeric_value_is_false():
    condition = RuleCondition(field="intencion", operator=">", value="consultar")
    assert evaluate_condition(condition, {"intencion": "zzz"}) is False


def test_evaluate_rule_requires_all_conditions_to_hold():
    rule = _rule(conditions=[
        RuleCondition(field="intencion", operator="=", value="consultar procedimiento"),
        RuleCondition(field="confianza", operator="<", value="0.70"),
    ])
    context_matches = {"intencion": "consultar procedimiento", "confianza": "0.5"}
    context_partial = {"intencion": "consultar procedimiento", "confianza": "0.9"}
    assert evaluate_rule(rule, context_matches) is True
    assert evaluate_rule(rule, context_partial) is False


def test_evaluate_rule_without_conditions_is_unconditional():
    rule = _rule(conditions=[])
    assert evaluate_rule(rule, {}) is True


def test_evaluate_rule_inactive_never_fires():
    rule = _rule(conditions=[], active=False)
    assert evaluate_rule(rule, {}) is False


def test_select_firing_action_returns_responder_when_nothing_fires():
    rules = [_rule(conditions=[RuleCondition(field="confianza", operator="<", value="0.1")], action=RuleActionType.CANALIZAR)]
    action, fired = select_firing_action(rules, {"confianza": "0.9"})
    assert action == RuleActionType.RESPONDER
    assert fired == []


def test_select_firing_action_picks_the_most_severe_among_several_firing_rules():
    rules = [
        _rule(name="pide aclaración", conditions=[], action=RuleActionType.ACLARAR),
        _rule(name="canaliza", conditions=[], action=RuleActionType.CANALIZAR),
    ]
    action, fired = select_firing_action(rules, {})
    assert action == RuleActionType.CANALIZAR
    assert {rule.name for rule in fired} == {"pide aclaración", "canaliza"}


# ---------- Ronda 87 (2026-10-02): sintaxis de condiciones ----------

def test_condicion_ignora_acentos_en_el_valor():
    condition = RuleCondition(field="intencion", operator="=", value="Solicitar asesoría")
    assert evaluate_condition(condition, {"intencion": "Solicitar asesoria"}) is True


def test_campo_con_acento_y_mayusculas_se_normaliza():
    condition = RuleCondition(field="Intención", operator="=", value="X")
    assert condition.field == "intencion"
    assert evaluate_condition(condition, {"intencion": "x"}) is True
    assert RuleCondition(field="Nivel riesgo", operator="=", value="alto").field == "nivel_riesgo"


def test_comillas_envolventes_no_forman_parte_del_valor():
    condition = RuleCondition(field="intencion", operator="=", value='"Solicitar asesor humano"')
    assert condition.value == "Solicitar asesor humano"
    assert evaluate_condition(condition, {"intencion": "Solicitar asesor humano"}) is True


def test_contiene_compara_siempre_como_texto():
    condition = RuleCondition(field="intencion", operator="contiene", value="2026")
    assert evaluate_condition(condition, {"intencion": "Inscripciones 2026"}) is True


def test_campo_desconocido_nunca_se_cumple_y_los_campos_validos_estan_documentados():
    from domain.conversational.rule_evaluation import CONTEXT_FIELDS

    assert set(CONTEXT_FIELDS) == {"intencion", "confianza", "nivel_riesgo", "variables_faltantes"}
    condition = RuleCondition(field="plantel", operator="=", value="Campus Norte")
    assert evaluate_condition(condition, {"intencion": "x", "confianza": "0.9"}) is False


def test_coma_decimal_se_acepta_como_numero():
    condition = RuleCondition(field="confianza", operator="<", value="0,70")
    assert evaluate_condition(condition, {"confianza": "0.5"}) is True
    assert evaluate_condition(condition, {"confianza": "0.9"}) is False
