import pytest

from domain.metadata.entities import CatalogEntry, FieldDataType, FieldDefinition, MetadataSchema


def test_catalog_backed_type_requires_catalog_id():
    with pytest.raises(ValueError):
        FieldDefinition(
            field_id="campus_id", schema_id="s1", display_name="Plantel",
            data_type=FieldDataType.CATALOGO_JERARQUICO,
        )


def test_catalog_backed_type_with_catalog_id_is_valid():
    field = FieldDefinition(
        field_id="campus_id", schema_id="s1", display_name="Plantel",
        data_type=FieldDataType.CATALOGO_JERARQUICO, catalog_id="cat-1",
    )
    assert field.catalog_id == "cat-1"


def test_free_text_type_does_not_require_catalog():
    field = FieldDefinition(
        field_id="notas", schema_id="s1", display_name="Notas", data_type=FieldDataType.TEXTO_LARGO,
    )
    assert field.catalog_id is None


@pytest.mark.parametrize("bad_field_id", ["con espacio", "acentó", "signo!", ""])
def test_invalid_field_id_formats_are_rejected(bad_field_id):
    with pytest.raises(ValueError):
        FieldDefinition(
            field_id=bad_field_id, schema_id="s1", display_name="X", data_type=FieldDataType.TEXTO,
        )


def test_metadata_schema_defaults_to_active_version_one():
    schema = MetadataSchema(project_id="p1")
    assert schema.version == 1
    assert schema.is_active is True


def test_catalog_entry_can_be_hierarchical():
    parent = CatalogEntry(catalog_id="c1", value_code="ADMISIONES", label="Admisiones")
    child = CatalogEntry(catalog_id="c1", value_code="REQUISITOS", label="Requisitos", parent_entry_id=parent.id)
    assert child.parent_entry_id == parent.id
