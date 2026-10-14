"""Pruebas de ui.ingestion.index_logic (Fase 4 de multimodalidad
nativa, RAG 3) -- lógica pura sin Qt."""
from ui.ingestion.index_logic import (
    INDEX_METHOD_IMAGE, INDEX_METHOD_TEXT, index_method_for_source_type,
)


def test_index_method_for_image_source_type_is_index_image_source():
    assert index_method_for_source_type("imagen_nativa") == INDEX_METHOD_IMAGE


def test_index_method_for_other_source_types_is_index_source():
    assert index_method_for_source_type("pdf") == INDEX_METHOD_TEXT
    assert index_method_for_source_type("docx") == INDEX_METHOD_TEXT
    assert index_method_for_source_type("api") == INDEX_METHOD_TEXT
