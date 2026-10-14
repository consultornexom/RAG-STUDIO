"""Pruebas unitarias del cargador dinámico de complementos (Etapa 8) --
usa clases reales ya existentes en el proyecto como "complementos de
prueba", en vez de dobles, para confirmar que la carga funciona contra
código de verdad, no solo contra una simulación."""
import pytest

from domain.plugins.entities import Plugin, PluginKind
from domain.plugins.exceptions import PluginLoadError
from domain.plugins.loader import expected_contract_label, load_and_validate, load_entry_point


def test_load_entry_point_resolves_a_real_class():
    cls = load_entry_point("infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider")
    assert cls.__name__ == "FastEmbedEmbeddingProvider"


def test_load_entry_point_rejects_missing_colon():
    with pytest.raises(PluginLoadError):
        load_entry_point("sin_dos_puntos")


def test_load_entry_point_rejects_unimportable_module():
    with pytest.raises(PluginLoadError):
        load_entry_point("no.such.module:Whatever")


def test_load_entry_point_rejects_missing_attribute():
    with pytest.raises(PluginLoadError):
        load_entry_point("domain.plugins.entities:NoExiste")


def test_load_and_validate_accepts_a_real_embedding_provider_for_proveedor():
    plugin = Plugin(
        kind=PluginKind.PROVEEDOR, code="x", name="x",
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    cls = load_and_validate(plugin)
    assert cls.__name__ == "FastEmbedEmbeddingProvider"


def test_load_and_validate_accepts_a_real_text_extractor_for_importador():
    plugin = Plugin(
        kind=PluginKind.IMPORTADOR, code="x", name="x",
        entry_point="infrastructure.extraction.text_extractors:TxtExtractor",
    )
    cls = load_and_validate(plugin)
    assert cls.__name__ == "TxtExtractor"


def test_load_and_validate_rejects_wrong_contract():
    plugin = Plugin(
        kind=PluginKind.PROVEEDOR, code="x", name="x",
        entry_point="infrastructure.extraction.text_extractors:TxtExtractor",
    )
    with pytest.raises(PluginLoadError):
        load_and_validate(plugin)


def test_load_and_validate_ok_for_plantilla_without_entry_point():
    plugin = Plugin(kind=PluginKind.PLANTILLA, code="x", name="x", config={"campos": ["plantel"]})
    load_and_validate(plugin)  # no debe lanzar


def test_expected_contract_label_mentions_the_real_port_for_each_code_kind():
    assert "EmbeddingProvider" in expected_contract_label(PluginKind.PROVEEDOR)
    assert "TextExtractor" in expected_contract_label(PluginKind.IMPORTADOR)
    assert "CustomEvaluator" in expected_contract_label(PluginKind.EVALUADOR)
    assert "sin contrato" in expected_contract_label(PluginKind.PLANTILLA)
