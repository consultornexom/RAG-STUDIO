"""Pruebas unitarias del comparador de resultados de búsqueda
(resaltado de coincidencias). Lógica pura, sin PySide6 -- se puede
correr en cualquier entorno, incluso sin las bibliotecas nativas de Qt
(libEGL/libGL) que sí requiere `ui/ingestion/panel.py`."""
from html import escape as html_escape

from ui.ingestion.search_highlighting import extract_highlight_terms, highlight_terms


# ---------- extract_highlight_terms ----------

def test_extract_highlight_terms_filters_short_words_and_stopwords():
    # Caso real: "Métodos Numéricos y Matlab" -- "y" es stopword de 1
    # letra, el resto son palabras con señal real.
    terms = extract_highlight_terms("Métodos Numéricos y Matlab")
    assert terms == ["Métodos", "Numéricos", "Matlab"]


def test_extract_highlight_terms_excludes_common_short_connectors():
    terms = extract_highlight_terms("el gato y el perro de la casa")
    # "gato", "perro", "casa" tienen longitud >=3 y no son stopwords;
    # "el", "y", "de", "la" sí lo son (o son demasiado cortas).
    assert terms == ["gato", "perro", "casa"]


def test_extract_highlight_terms_empty_query_returns_empty_list():
    assert extract_highlight_terms("") == []
    assert extract_highlight_terms("   ") == []


def test_extract_highlight_terms_ignores_case_for_stopword_matching():
    terms = extract_highlight_terms("DE la Cuatrimestre")
    assert terms == ["Cuatrimestre"]


# ---------- highlight_terms ----------

def test_highlight_terms_wraps_case_insensitive_matches():
    text = html_escape("Programación • Métodos Numéricos y Matlab • Metrología")
    result = highlight_terms(text, ["metodos numericos"])  # sin coincidencia exacta por acentos
    assert result == text  # no debe fallar ni alterar el texto si no hay match exacto

    result2 = highlight_terms(text, ["Métodos", "Matlab"])
    assert '<span style="background-color:#fff2a8;">Métodos</span>' in result2
    assert '<span style="background-color:#fff2a8;">Matlab</span>' in result2
    # el resto del texto permanece intacto
    assert "Programación" in result2
    assert "Metrología" in result2


def test_highlight_terms_with_no_terms_returns_text_unchanged():
    text = html_escape("Cualquier texto de fragmento")
    assert highlight_terms(text, []) == text


def test_highlight_terms_ignores_empty_string_terms():
    text = html_escape("Álgebra Lineal")
    assert highlight_terms(text, ["", ""]) == text


def test_highlight_terms_does_not_reintroduce_unescaped_html():
    # El texto ya viene escapado -- confirmar que highlight_terms no
    # rompe las entidades existentes (p. ej. si el fragmento original
    # tenía un "<" o "&" literal).
    text = html_escape("Requisitos < 3 & > 1 materias")
    result = highlight_terms(text, ["materias"])
    assert "&lt;" in result
    assert "&amp;" in result
    assert '<span style="background-color:#fff2a8;">materias</span>' in result


def test_highlight_terms_matches_multiple_occurrences():
    text = html_escape("Cuatrimestre uno, cuatrimestre dos, CUATRIMESTRE tres")
    result = highlight_terms(text, ["cuatrimestre"])
    assert result.count('<span style="background-color:#fff2a8;">') == 3
