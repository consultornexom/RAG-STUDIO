"""Punto 10 de Validacion_observaciones_RAG_STUDIO.md: fields_applicable_to
es el punto único que decide qué campos del esquema aplican a una
fuente según su document_type_code."""
from domain.metadata.entities import FieldDataType, FieldDefinition, fields_applicable_to


def _field(field_id: str, document_type_code=None) -> FieldDefinition:
    return FieldDefinition(
        field_id=field_id, schema_id="s1", display_name=field_id, data_type=FieldDataType.TEXTO,
        document_type_code=document_type_code,
    )


def test_field_document_type_code_defaults_to_none():
    assert _field("tel").document_type_code is None


def test_generic_field_applies_to_any_document_type():
    generic = _field("nombre")
    assert fields_applicable_to([generic], "contactos") == [generic]
    assert fields_applicable_to([generic], "requisitos_admision") == [generic]


def test_typed_field_only_applies_to_matching_document_type():
    contactos_field = _field("tel", document_type_code="contactos")
    assert fields_applicable_to([contactos_field], "contactos") == [contactos_field]
    assert fields_applicable_to([contactos_field], "requisitos_admision") == []


def test_mixed_fields_are_filtered_independently():
    generic = _field("nombre")
    contactos_field = _field("tel", document_type_code="contactos")
    admision_field = _field("promedio_minimo", document_type_code="requisitos_admision")
    fields = [generic, contactos_field, admision_field]

    assert fields_applicable_to(fields, "contactos") == [generic, contactos_field]
    assert fields_applicable_to(fields, "requisitos_admision") == [generic, admision_field]
    assert fields_applicable_to(fields, "default") == [generic]
