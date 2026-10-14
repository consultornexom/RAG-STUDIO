"""Pruebas de ui.sources.image_source_logic (Fase 4 de multimodalidad
nativa, RAG 3) -- lógica pura sin Qt, mismo patrón que
test_conversational_parsing.py/test_gate_status_logic.py."""
from ui.sources.image_source_logic import image_file_dialog_filter, image_preview_placeholder_text


# ---------- image_file_dialog_filter ----------

def test_image_file_dialog_filter_restricts_to_image_extensions_for_image_type():
    filtro = image_file_dialog_filter("imagen_nativa")
    assert "*.png" in filtro
    assert "*.jpg" in filtro


def test_image_file_dialog_filter_is_empty_for_other_source_types():
    assert image_file_dialog_filter("pdf") == ""
    assert image_file_dialog_filter("docx") == ""
    assert image_file_dialog_filter("api") == ""


# ---------- image_preview_placeholder_text ----------

def test_image_preview_placeholder_says_not_applicable_for_non_image_type():
    text = image_preview_placeholder_text("pdf", "/tmp/algo.pdf")
    assert text is not None
    assert "no aplica" in text


def test_image_preview_placeholder_asks_to_choose_a_file_when_location_is_empty():
    text = image_preview_placeholder_text("imagen_nativa", "")
    assert text is not None
    assert "elige un archivo" in text


def test_image_preview_placeholder_asks_to_choose_a_file_when_location_is_blank():
    text = image_preview_placeholder_text("imagen_nativa", "   ")
    assert text is not None


def test_image_preview_placeholder_returns_none_when_ready_to_attempt_a_real_load():
    # source_type es Imagen y location no está vacía -- corresponde
    # intentar un QPixmap real, algo que esta función deliberadamente
    # no sabe hacer (ver docstring del módulo).
    assert image_preview_placeholder_text("imagen_nativa", "/tmp/foto.png") is None
