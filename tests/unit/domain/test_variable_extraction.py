"""Ronda 89: detección de valores de variables en el texto de la consulta."""
from domain.conversational.variable_extraction import (
    ValueCandidate, alias_forms, extract_variable_values, remove_spans,
)


def _programas(*pares):
    return [ValueCandidate(code, alias_forms(label, code)) for code, label in pares]


PROGRAMAS = _programas(
    ("gestion_profesional_de_proyectos", "Gestión Profesional de Proyectos"),
    ("psicologia", "Psicología"),
    ("psicologia_organizacional", "Psicología Organizacional"),
    ("justicia_laboral_i", "Justicia Laboral I"),
    ("justicia_laboral_ii", "Justicia Laboral II"),
    ("artes_plasticas", "Artes Plásticas"),
)


def test_detecta_el_programa_sin_acentos_ni_mayusculas():
    r = extract_variable_values(
        "¿Cuál es el objetivo del Diplomado de Alta Especialidad en gestion profesional de PROYECTOS?",
        {"programa_academico": PROGRAMAS},
    )
    assert r.detected == {"programa_academico": "gestion_profesional_de_proyectos"}


def test_gana_la_mencion_mas_larga():
    r = extract_variable_values("plan de estudios de Psicología Organizacional", {"p": PROGRAMAS})
    assert r.detected == {"p": "psicologia_organizacional"}


def test_compara_palabras_completas():
    r = extract_variable_values("requisitos de Justicia Laboral II", {"p": PROGRAMAS})
    assert r.detected == {"p": "justicia_laboral_ii"}
    assert extract_variable_values("arte plástico", {"p": PROGRAMAS}).detected == {}


def test_dos_programas_igual_de_especificos_es_ambiguo_y_no_se_llena():
    candidatos = PROGRAMAS + _programas(("finanzas", "Finanzas"))
    r = extract_variable_values("¿Psicología o Finanzas?", {"p": candidatos})
    assert r.detected == {}
    assert r.ambiguous == {"p": ["finanzas", "psicologia"]}


def test_el_codigo_con_guiones_bajos_tambien_cuenta_como_alias():
    r = extract_variable_values("info de gestion_profesional_de_proyectos", {"p": PROGRAMAS})
    assert r.detected == {"p": "gestion_profesional_de_proyectos"}


def test_remove_spans_conserva_el_resto_de_la_consulta():
    q = "¿Cuál es el objetivo de Gestión Profesional de Proyectos?"
    r = extract_variable_values(q, {"p": PROGRAMAS})
    assert remove_spans(q, r.spans["p"]) == "¿Cuál es el objetivo ?"


def test_remove_spans_quita_los_conectores_que_quedan_colgando():
    """Ronda 91: "la licenciatura en Derecho" sin "licenciatura" ni
    "Derecho" ya no deja "la en"."""
    q = "¿Qué conocimientos obtiene quien termina la licenciatura en Derecho?"
    spans = [(q.index("licenciatura"), q.index("licenciatura") + 12), (q.index("Derecho"), q.index("Derecho") + 7)]
    assert remove_spans(q, spans) == "¿Qué conocimientos obtiene quien termina ?"
    q2 = "Dame información de Derecho"
    assert remove_spans(q2, [(20, 27)]) == "Dame información"
