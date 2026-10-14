"""Pruebas del vocabulario de application.documents.options -- en
particular TERMINAL_VALIDATION_STATUS_VALUES (Ronda 5, hallazgo real de
usuario), que ui.sources.panel usa para advertir antes de aplicar una
transición de estado de validación sin retorno."""
from application.documents.options import (
    IMAGE_SOURCE_TYPE_VALUE, SOURCE_TYPE_OPTIONS, TERMINAL_VALIDATION_STATUS_VALUES, VALIDATION_STATUS_OPTIONS,
)


def test_terminal_validation_status_values_are_plain_strings():
    assert TERMINAL_VALIDATION_STATUS_VALUES == {"sustituido", "vencido", "rechazado"}
    assert all(isinstance(v, str) for v in TERMINAL_VALIDATION_STATUS_VALUES)


def test_terminal_validation_status_values_is_subset_of_all_options():
    assert TERMINAL_VALIDATION_STATUS_VALUES <= set(VALIDATION_STATUS_OPTIONS)


# ---------- IMAGE_SOURCE_TYPE_VALUE (Fase 4 de multimodalidad nativa, RAG 3) ----------

def test_image_source_type_value_matches_historic_domain_value():
    assert IMAGE_SOURCE_TYPE_VALUE == "imagen_nativa"


def test_image_source_type_value_is_one_of_the_selectable_source_types():
    # El selector de tipo de fuente del diálogo de alta (ui.sources.panel)
    # se llena con SOURCE_TYPE_OPTIONS -- si este valor no estuviera ahí,
    # la comparación en ui.ingestion.panel/ui.sources.panel nunca podría
    # coincidir con nada seleccionable de verdad.
    assert IMAGE_SOURCE_TYPE_VALUE in SOURCE_TYPE_OPTIONS
