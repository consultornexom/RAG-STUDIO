"""Pruebas unitarias de la normalización de texto (RAG STUDIO.odt:
paso propio entre "Extracción" y "Fragmentación" del alcance mínimo
obligatorio de la primera versión)."""
from domain.ingestion.normalization import normalize_text


def test_unifies_windows_and_mac_line_endings_to_unix():
    assert normalize_text("uno\r\ndos\rtres") == "uno\ndos\ntres"


def test_strips_trailing_whitespace_per_line():
    assert normalize_text("uno   \ndos\t\ntres") == "uno\ndos\ntres"


def test_collapses_three_or_more_blank_lines_into_exactly_two():
    assert normalize_text("uno\n\n\n\n\ndos") == "uno\n\ndos"


def test_does_not_touch_a_single_blank_line():
    assert normalize_text("uno\n\ndos") == "uno\n\ndos"


def test_removes_control_characters_but_keeps_tab_and_newline():
    assert normalize_text("uno\x00\x01dos\ttres\n") == "unodos\ttres"


def test_normalizes_unicode_to_nfc():
    decomposed = "e" + "́"  # "e" + acento combinante
    assert normalize_text(decomposed) == "é"
    assert len(normalize_text(decomposed)) == 1


def test_strips_leading_and_trailing_whitespace_of_the_whole_text():
    assert normalize_text("\n\n  contenido  \n\n") == "contenido"


def test_does_not_touch_internal_spacing_of_a_markdown_table():
    table = "| codigo | nombre |\n| --- | --- |\n| ISC | Ingeniería en Sistemas |"
    assert normalize_text(table) == table


def test_is_idempotent():
    text = "Titulo   \r\n\r\n\r\n\r\nParrafo.  \n\n\nFinal."
    once = normalize_text(text)
    twice = normalize_text(once)
    assert once == twice


def test_empty_string_stays_empty():
    assert normalize_text("") == ""
