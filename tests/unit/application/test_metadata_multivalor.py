"""Ronda 97 (hallazgo real de NEXOM, AGENTE UDL, prioridad alta): un campo
`seleccion_multiple` con catálogo y "Permite varios valores" solo podía
guardar UN valor desde "Valores por fuente": guardar torres_landa
sustituía a hilario_medina. Pruebas de la capa de aplicación: varios
valores, agregar sin reemplazar, quitar uno solo, asignación masiva."""
import pytest

from application.documents.service import DocumentService
from application.metadata.service import MetadataService
from domain.documents.entities import SourceType
from domain.metadata.entities import FieldDataType, join_values, split_stored_values
from domain.metadata.exceptions import (
    FieldDefinitionNotFoundError,
    InvalidMetadataValueError,
    SourceMetadataValueNotFoundError,
)

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryExtractionRepository
from .fakes_metadata import (
    InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository,
)

P = "p1"


@pytest.fixture
def fx():
    sources = InMemorySourceRepository()
    meta = MetadataService(
        InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(), InMemorySourceMetadataRepository(), sources,
    )
    docs = DocumentService(sources, InMemoryExtractionRepository())
    schema = meta.create_schema(P)
    catalog = meta.create_catalog(P, "campus_udl")
    meta.add_catalog_entry(P, catalog.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(P, catalog.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(
        P, schema.id, "campus", "Campus o plantel", FieldDataType.SELECCION_MULTIPLE,
        multiple=True, filterable=True, inherited_by_chunks=True, catalog_id=catalog.id,
    )
    nivel = meta.create_catalog(P, "nivel")
    meta.add_catalog_entry(P, nivel.id, "bachillerato", "Bachillerato")
    meta.add_field_definition(
        P, schema.id, "nivel_academico", "Nivel", FieldDataType.SELECCION_UNICA, catalog_id=nivel.id,
    )
    src = docs.register_source(P, "requisitos_ingreso.md", SourceType.MARKDOWN)
    return meta, docs, schema.id, src.id


def _valor(meta, source_id, field_id="campus"):
    return {v.field_id: v.value for v in meta.list_source_metadata_values(P, source_id)}.get(field_id)


def test_escenario_de_aceptacion_ambos_planteles_quedan_guardados(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"])
    assert split_stored_values(_valor(meta, src)) == ["hilario_medina", "torres_landa"]


def test_agregar_conserva_el_valor_anterior(fx):
    """Reproduce la incidencia: guardar el segundo plantel ya no sustituye al primero."""
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina"])
    meta.set_source_metadata_value(P, sid, src, "campus", ["torres_landa"], mode="agregar")
    assert split_stored_values(_valor(meta, src)) == ["hilario_medina", "torres_landa"]


def test_agregar_no_duplica(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina"])
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"], mode="agregar")
    assert _valor(meta, src) == "hilario_medina|torres_landa"


def test_reemplazar_deja_exactamente_lo_indicado(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"])
    meta.set_source_metadata_value(P, sid, src, "campus", ["torres_landa"])
    assert _valor(meta, src) == "torres_landa"


def test_valores_repetidos_en_la_lista_se_guardan_una_vez(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["torres_landa", "torres_landa", "hilario_medina"])
    assert _valor(meta, src) == "torres_landa|hilario_medina"


def test_cada_valor_se_valida_contra_el_catalogo_y_no_se_guarda_nada_si_uno_falla(fx):
    meta, _, sid, src = fx
    with pytest.raises(InvalidMetadataValueError, match="no_existe"):
        meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "no_existe"])
    assert _valor(meta, src) is None


@pytest.mark.parametrize("malo", ["", "   ", "hilario_medina|torres_landa"])
def test_valor_vacio_o_con_separador_se_rechaza(fx, malo):
    meta, _, sid, src = fx
    with pytest.raises(InvalidMetadataValueError):
        meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", malo])
    assert _valor(meta, src) is None


def test_agregar_en_campo_de_un_solo_valor_se_rechaza(fx):
    meta, _, sid, src = fx
    with pytest.raises(InvalidMetadataValueError, match="no admite varios valores"):
        meta.set_source_metadata_value(P, sid, src, "nivel_academico", "bachillerato", mode="agregar")


def test_agregar_sin_valores_se_rechaza(fx):
    meta, _, sid, src = fx
    with pytest.raises(InvalidMetadataValueError, match="ningún valor que agregar"):
        meta.set_source_metadata_value(P, sid, src, "campus", [], mode="agregar")


def test_modo_desconocido_se_rechaza(fx):
    meta, _, sid, src = fx
    with pytest.raises(InvalidMetadataValueError, match="Modo de asignación"):
        meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina"], mode="sumar")


def test_campo_de_un_solo_valor_sigue_igual(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "nivel_academico", "bachillerato")
    assert _valor(meta, src, "nivel_academico") == "bachillerato"
    with pytest.raises(InvalidMetadataValueError):
        meta.set_source_metadata_value(P, sid, src, "nivel_academico", ["bachillerato", "bachillerato"])


# ---------- quitar un valor individual ----------

def test_quitar_un_valor_conserva_los_demas(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"])
    restantes = meta.remove_source_metadata_value_item(P, sid, src, "campus", "hilario_medina")
    assert restantes == ["torres_landa"]
    assert _valor(meta, src) == "torres_landa"


def test_quitar_el_ultimo_valor_deja_el_campo_sin_asignar_y_queda_en_historial(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["torres_landa"])
    assert meta.remove_source_metadata_value_item(P, sid, src, "campus", "torres_landa") == []
    assert _valor(meta, src) is None
    historial = meta.list_value_history(P, src, "campus")
    assert historial[0].previous_value == "torres_landa" and historial[0].new_value is None


def test_quitar_un_valor_queda_en_historial(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"])
    meta.remove_source_metadata_value_item(P, sid, src, "campus", "torres_landa")
    ultimo = meta.list_value_history(P, src, "campus")[0]
    assert (ultimo.previous_value, ultimo.new_value) == ("hilario_medina|torres_landa", "hilario_medina")


def test_quitar_un_valor_que_no_esta_asignado_da_error_claro(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina"])
    with pytest.raises(SourceMetadataValueNotFoundError):
        meta.remove_source_metadata_value_item(P, sid, src, "campus", "torres_landa")
    assert _valor(meta, src) == "hilario_medina"


def test_quitar_un_valor_individual_solo_en_campos_multivalor(fx):
    meta, _, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "nivel_academico", "bachillerato")
    with pytest.raises(InvalidMetadataValueError):
        meta.remove_source_metadata_value_item(P, sid, src, "nivel_academico", "bachillerato")
    with pytest.raises(FieldDefinitionNotFoundError):
        meta.remove_source_metadata_value_item(P, sid, src, "no_existe", "x")


# ---------- asignación masiva ----------

def test_masivo_agregar_conserva_lo_que_cada_fuente_ya_tenia(fx):
    meta, docs, sid, src = fx
    otra = docs.register_source(P, "becas.md", SourceType.MARKDOWN).id
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina"])
    result = meta.bulk_set_source_metadata_value(P, sid, [src, otra], "campus", ["torres_landa"], mode="agregar")
    assert result.updated_count == 2
    assert _valor(meta, src) == "hilario_medina|torres_landa"
    assert _valor(meta, otra) == "torres_landa"


def test_masivo_con_varios_valores_los_guarda_todos(fx):
    meta, docs, sid, src = fx
    otra = docs.register_source(P, "becas.md", SourceType.MARKDOWN).id
    meta.bulk_set_source_metadata_value(P, sid, [src, otra], "campus", ["hilario_medina", "torres_landa"])
    assert _valor(meta, src) == _valor(meta, otra) == "hilario_medina|torres_landa"


def test_masivo_reemplazar_es_el_comportamiento_por_defecto(fx):
    meta, docs, sid, src = fx
    meta.set_source_metadata_value(P, sid, src, "campus", ["hilario_medina", "torres_landa"])
    meta.bulk_set_source_metadata_value(P, sid, [src], "campus", ["torres_landa"])
    assert _valor(meta, src) == "torres_landa"


def test_masivo_valida_antes_de_escribir(fx):
    meta, docs, sid, src = fx
    with pytest.raises(InvalidMetadataValueError):
        meta.bulk_set_source_metadata_value(P, sid, [src], "campus", ["torres_landa", "otro"], mode="agregar")
    assert _valor(meta, src) is None


def test_funciones_de_serializacion():
    assert split_stored_values(None) == []
    assert split_stored_values(" a | b |a||") == ["a", "b"]
    assert join_values(["a", "b"]) == "a|b"
