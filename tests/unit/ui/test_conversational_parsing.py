"""Pruebas unitarias de ui.conversational.parsing (funciones puras,
sin PySide6 -- se pueden correr en cualquier entorno, incluso sin
libEGL/libGL, ver ui/ingestion/search_highlighting.py)."""
from ui.conversational.parsing import (
    format_conditions, format_key_value_lines, parse_conditions, parse_csv, parse_key_value_lines, parse_lines,
    parse_provided_variables,
)


def test_parse_lines_ignores_blank_lines():
    assert parse_lines("uno\n\n  \ndos\n") == ["uno", "dos"]


def test_parse_csv_trims_and_drops_empty_items():
    assert parse_csv("programa, plantel ,, modalidad") == ["programa", "plantel", "modalidad"]


def test_parse_key_value_lines_ignores_lines_without_separator():
    result = parse_key_value_lines("plantel: ¿En qué plantel?\nlinea sin separador\nprograma:¿Qué programa?")
    assert result == {"plantel": "¿En qué plantel?", "programa": "¿Qué programa?"}


def test_parse_provided_variables_from_single_line_csv():
    assert parse_provided_variables("programa=Ingeniería, plantel=Centro") == {
        "programa": "Ingeniería", "plantel": "Centro",
    }


def test_parse_provided_variables_ignores_items_without_equals():
    assert parse_provided_variables("programa=Ingeniería, esto no tiene igual") == {"programa": "Ingeniería"}


def test_parse_conditions_recognizes_each_operator():
    text = "\n".join([
        "confianza < 0.70",
        "confianza <= 0.70",
        "confianza > 0.70",
        "confianza >= 0.70",
        "intencion != consultar",
        "intencion = consultar",
        "intencion contiene consultar",
    ])
    conditions = parse_conditions(text)
    assert [c["operator"] for c in conditions] == ["<", "<=", ">", ">=", "!=", "=", "contiene"]
    assert all(c["field"] == "confianza" or c["field"] == "intencion" for c in conditions)


def test_parse_conditions_ignores_lines_without_a_recognized_operator():
    conditions = parse_conditions("confianza < 0.70\nesto no es una condición válida")
    assert len(conditions) == 1
    assert conditions[0] == {"field": "confianza", "operator": "<", "value": "0.70"}


def test_parse_conditions_prefers_two_character_operators_over_prefixes():
    # "<=" no debe interpretarse como "<" seguido de un valor "= 0.70".
    conditions = parse_conditions("confianza <= 0.70")
    assert conditions == [{"field": "confianza", "operator": "<=", "value": "0.70"}]


def test_format_key_value_lines_matches_the_input_format_of_parse_key_value_lines():
    # Ajuste funcional del 2026-09-03 (hallazgo real de usuario, ver
    # bitácora): edición completa de intenciones -- format_key_value_lines
    # precarga Intent.clarifying_questions en el formulario de edición.
    pairs = {"plantel": "¿En qué plantel?", "programa": "¿Qué programa?"}
    text = format_key_value_lines(pairs)
    assert text == "plantel: ¿En qué plantel?\nprograma: ¿Qué programa?"
    assert parse_key_value_lines(text) == pairs


def test_format_key_value_lines_empty_dict_is_empty_string():
    assert format_key_value_lines({}) == ""


def test_format_conditions_matches_the_input_format_of_parse_conditions():
    class _FakeOperator:
        def __init__(self, value):
            self.value = value

    class _FakeCondition:
        def __init__(self, field, operator, value):
            self.field = field
            self.operator = _FakeOperator(operator)
            self.value = value

    conditions = [_FakeCondition("confianza", "<", "0.70")]
    assert format_conditions(conditions) == "confianza < 0.70"


# ---------- Ronda 87 (2026-10-02): validación de condiciones antes de guardar ----------

from ui.conversational.parsing import (  # noqa: E402
    condition_syntax_help, describe_condition_problems, parse_conditions_detailed,
)

_CAMPOS = {"intencion": "", "confianza": "", "nivel_riesgo": "", "variables_faltantes": ""}


def test_se_usa_el_primer_operador_de_la_linea():
    conditions, _ = parse_conditions_detailed("intencion contiene a=b")
    assert conditions == [{"field": "intencion", "operator": "contiene", "value": "a=b"}]


def test_contiene_no_distingue_mayusculas():
    conditions, _ = parse_conditions_detailed("intencion CONTIENE asesor")
    assert conditions == [{"field": "intencion", "operator": "contiene", "value": "asesor"}]


def test_lineas_sin_operador_se_reportan_en_vez_de_ignorarse():
    conditions, unrecognized = parse_conditions_detailed("intencion es asesor humano\nconfianza < 0.7")
    assert unrecognized == ["intencion es asesor humano"]
    assert conditions == [{"field": "confianza", "operator": "<", "value": "0.7"}]


def test_describe_problemas_bloquea_lineas_invalidas_y_advierte_campos_desconocidos():
    errors, warnings = describe_condition_problems(
        "Solicitud de asesor humano\nplantel = Campus Norte\nIntención = Solicitar asesor", _CAMPOS,
    )
    assert len(errors) == 1 and "Solicitud de asesor humano" in errors[0]
    assert len(warnings) == 1 and "plantel" in warnings[0]  # "Intención" se reconoce como intencion


def test_texto_vacio_no_tiene_problemas():
    assert describe_condition_problems("", _CAMPOS) == ([], [])


def test_ayuda_lista_operadores_campos_y_ejemplos():
    texto = condition_syntax_help({"intencion": "Nombre de la intención"})
    for fragmento in ("contiene", "intencion: Nombre de la intención", "confianza < 0.45"):
        assert fragmento in texto
