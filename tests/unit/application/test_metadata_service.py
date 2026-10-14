import pytest

from application.documents.service import DocumentService
from application.metadata.service import MetadataService
from domain.documents.entities import SourceType
from domain.metadata.entities import FieldDataType
from domain.metadata.exceptions import (
    CatalogEntryInUseError,
    CatalogEntryNotFoundError,
    CatalogInUseError,
    CatalogNotFoundError,
    CatalogRequiredForFieldTypeError,
    DuplicateCatalogEntryError,
    DuplicateFieldIdError,
    FieldDefinitionNotFoundError,
    FieldInUseError,
    InvalidMetadataValueError,
    SchemaAlreadyExistsError,
    SourceMetadataValueNotFoundError,
)

from .fakes_documents import InMemorySourceRepository
from .fakes_ingestion import InMemoryExtractionRepository
from .fakes_metadata import (
    InMemoryCatalogRepository, InMemoryMetadataSchemaRepository, InMemorySourceMetadataRepository,
)


@pytest.fixture
def services():
    source_repository = InMemorySourceRepository()
    metadata_service = MetadataService(
        InMemoryMetadataSchemaRepository(), InMemoryCatalogRepository(),
        InMemorySourceMetadataRepository(), source_repository,
    )
    document_service = DocumentService(source_repository, InMemoryExtractionRepository())
    return metadata_service, document_service


def test_create_schema_then_duplicate_raises(services):
    metadata_service, _ = services
    metadata_service.create_schema("p1")
    with pytest.raises(SchemaAlreadyExistsError):
        metadata_service.create_schema("p1")


def test_add_field_requires_existing_catalog(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    with pytest.raises(CatalogNotFoundError):
        metadata_service.add_field_definition(
            "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO,
            catalog_id="no-existe",
        )


def test_add_field_of_catalog_backed_type_without_catalog_id_raises_clear_domain_error(services):
    """Hallazgo real de validación visual: antes de este chequeo, este
    caso lanzaba pydantic.ValidationError crudo (el model_validator de
    FieldDefinition), que la UI mostraba tal cual -- un mensaje técnico
    en vez de un error de dominio limpio como el resto de la app."""
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    with pytest.raises(CatalogRequiredForFieldTypeError):
        metadata_service.add_field_definition(
            "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO,
        )


def test_update_field_to_catalog_backed_type_without_catalog_id_raises_clear_domain_error(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    with pytest.raises(CatalogRequiredForFieldTypeError):
        metadata_service.update_field_definition("p1", schema.id, "campus_id", "Plantel", catalog_id=None)


def test_add_field_duplicate_field_id_raises(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    with pytest.raises(DuplicateFieldIdError):
        metadata_service.add_field_definition("p1", schema.id, "topic", "Tema otra vez", FieldDataType.TEXTO)


def test_add_catalog_entry_duplicate_value_code_raises_a_clear_domain_error(services):
    # Auditoría profunda (ronda posterior a la 76, ver bitácora): antes
    # de esta ronda, un value_code repetido llegaba crudo hasta un
    # IntegrityError de SQLAlchemy (la base de datos ya lo impedía con
    # uq_catalog_entry_code) -- sin verificación previa, la UI/API no
    # recibía ningún error de dominio legible, a diferencia del mismo
    # caso ya cubierto para field_id (test_add_field_duplicate_field_id_raises).
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    with pytest.raises(DuplicateCatalogEntryError):
        metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida otra vez")


def test_set_value_rejects_value_outside_catalog(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    with pytest.raises(InvalidMetadataValueError):
        metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus_id", "OAXACA")

    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus_id", "MERIDA")


def test_set_value_rejects_multiple_values_when_not_allowed(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO, multiple=False)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    with pytest.raises(InvalidMetadataValueError):
        metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", ["becas", "admisiones"])


def test_bulk_set_source_metadata_value_updates_all_selected_sources(services):
    """Ronda 5, punto 21 (hallazgo real de usuario, vídeo 2): el mismo
    valor de un campo se aplica de una vez a varias fuentes."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source_a = document_service.register_source("p1", "Ficha A", SourceType.PDF)
    source_b = document_service.register_source("p1", "Ficha B", SourceType.PDF)

    result = metadata_service.bulk_set_source_metadata_value(
        "p1", schema.id, [source_a.id, source_b.id], "campus", "Campus Norte",
    )

    assert result.updated_count == 2
    assert result.skipped_count == 0
    values_a = metadata_service.list_source_metadata_values("p1", source_a.id)
    values_b = metadata_service.list_source_metadata_values("p1", source_b.id)
    assert values_a[0].value == "Campus Norte"
    assert values_b[0].value == "Campus Norte"


def test_bulk_set_source_metadata_value_skips_missing_source_but_continues(services):
    """Una fuente que ya no existe (pudo eliminarse entre que se armó la
    selección en la UI y que se ejecuta la asignación) se omite sin
    abortar el resto del lote -- mismo criterio que
    BulkSetDocumentTypeCode."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source_a = document_service.register_source("p1", "Ficha A", SourceType.PDF)

    result = metadata_service.bulk_set_source_metadata_value(
        "p1", schema.id, [source_a.id, "no-existe"], "campus", "Campus Norte",
    )

    assert result.updated_source_ids == [source_a.id]
    assert result.skipped_source_ids == ["no-existe"]


def test_bulk_set_source_metadata_value_invalid_value_raises_even_if_no_source_exists(services):
    """Auditoría posterior a la Ronda 5 (a petición del usuario, tras
    implementar el punto 21): la validación original ocurría dentro del
    bucle, solo para fuentes confirmadas como existentes -- si
    source_ids venía vacío, o ninguna de las fuentes listadas seguía
    existiendo, un field_id/valor inválido pasaba sin detectarse y el
    método devolvía un resultado vacío en silencio en vez de señalar el
    error de diseño del lote. Corregido validando antes del bucle,
    independientemente de qué fuentes existan."""
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO, required=True)

    with pytest.raises(InvalidMetadataValueError):
        metadata_service.bulk_set_source_metadata_value("p1", schema.id, [], "campus", [])

    with pytest.raises(FieldDefinitionNotFoundError):
        metadata_service.bulk_set_source_metadata_value(
            "p1", schema.id, ["no-existe-tampoco"], "campo-que-no-existe", "valor",
        )


def test_bulk_set_source_metadata_value_deduplicates_repeated_source_ids(services):
    """Un source_id repetido en la selección no debe procesarse dos
    veces ni inflar updated_count -- hallazgo de la misma auditoría."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source_a = document_service.register_source("p1", "Ficha A", SourceType.PDF)

    result = metadata_service.bulk_set_source_metadata_value(
        "p1", schema.id, [source_a.id, source_a.id], "campus", "Campus Norte",
    )

    assert result.updated_source_ids == [source_a.id]
    assert result.updated_count == 1


def test_bulk_set_source_metadata_value_invalid_value_aborts_before_writing_any(services):
    """Un valor fuera de catálogo es un error de diseño del lote (mismo
    campo/valor para todas las fuentes), no de una fuente puntual: debe
    abortar toda la operación sin dejar ninguna fuente actualizada."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source_a = document_service.register_source("p1", "Ficha A", SourceType.PDF)
    source_b = document_service.register_source("p1", "Ficha B", SourceType.PDF)

    with pytest.raises(InvalidMetadataValueError):
        metadata_service.bulk_set_source_metadata_value(
            "p1", schema.id, [source_a.id, source_b.id], "campus_id", "OAXACA",
        )

    assert metadata_service.list_source_metadata_values("p1", source_a.id) == []
    assert metadata_service.list_source_metadata_values("p1", source_b.id) == []


def test_delete_source_metadata_value_removes_it(services):
    """Ronda 6, punto 23 (hallazgo real de usuario, vídeo 3): antes no
    había forma de desasociar un valor ya guardado -- solo
    set_source_metadata_value (upsert), nunca un borrado real."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus", "Campus Norte")

    metadata_service.delete_source_metadata_value("p1", source.id, "campus")

    assert metadata_service.list_source_metadata_values("p1", source.id) == []


def test_delete_source_metadata_value_missing_value_raises(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    with pytest.raises(SourceMetadataValueNotFoundError):
        metadata_service.delete_source_metadata_value("p1", source.id, "campus")


def test_delete_source_metadata_value_records_history_with_new_value_none(services):
    """El borrado queda en el historial igual que cualquier otro cambio
    (ítem 5 de la evaluación de madurez post-8-etapas) -- new_value=None
    identifica que el campo quedó sin asignar, no que se guardó un
    valor vacío."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "campus", "Plantel", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus", "Campus Norte")

    metadata_service.delete_source_metadata_value("p1", source.id, "campus")

    history = metadata_service.list_value_history("p1", source.id)
    assert history[0].previous_value == "Campus Norte"
    assert history[0].new_value is None


def test_coverage_report_reflects_required_fields(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition(
        "p1", schema.id, "topic", "Tema", FieldDataType.TEXTO, required=True,
    )
    complete = document_service.register_source("p1", "Completa", SourceType.PDF)
    document_service.register_source("p1", "Incompleta", SourceType.PDF)  # cuenta para total_sources, sin describir
    metadata_service.set_source_metadata_value("p1", schema.id, complete.id, "topic", "becas")

    report = metadata_service.get_coverage_report("p1")
    assert report["total_sources"] == 2
    assert report["sources_fully_described"] == 1
    assert report["coverage_ratio"] == 0.5
    assert report["meets_acceptance_threshold"] is False


def test_coverage_report_with_no_sources_is_reported_explicitly(services):
    metadata_service, _ = services
    metadata_service.create_schema("p1")
    report = metadata_service.get_coverage_report("p1")
    assert report["total_sources"] == 0
    assert report["coverage_ratio"] is None
    assert report["meets_acceptance_threshold"] is False


# ---------- document_type_code (punto 10 de Validacion_observaciones_RAG_STUDIO.md) ----------

def test_coverage_report_ignores_required_field_from_other_document_type(services):
    """Caso real reportado por el usuario: un campo obligatorio pensado
    para "requisitos de admisión" no debe impedir que una fuente de
    "contactos" cuente como completamente descrita -- antes de acotar
    los campos por document_type_code, este caso nunca podía llegar al
    100% de cobertura aunque estuviera bien descrito para su propio
    tipo."""
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition(
        "p1", schema.id, "tel", "Teléfono", FieldDataType.TEXTO, required=True,
        document_type_code="contactos",
    )
    metadata_service.add_field_definition(
        "p1", schema.id, "promedio_minimo", "Promedio mínimo", FieldDataType.TEXTO, required=True,
        document_type_code="requisitos_admision",
    )
    contacto = document_service.register_source(
        "p1", "contactos.jpeg", SourceType.MARKDOWN, document_type_code="contactos",
    )
    metadata_service.set_source_metadata_value("p1", schema.id, contacto.id, "tel", "9999999999")

    report = metadata_service.get_coverage_report("p1")
    assert report["total_sources"] == 1
    assert report["sources_fully_described"] == 1
    assert report["coverage_ratio"] == 1.0


def test_list_applicable_fields_returns_generic_and_matching_type_only(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "idioma", "Idioma", FieldDataType.TEXTO)
    metadata_service.add_field_definition(
        "p1", schema.id, "tel", "Teléfono", FieldDataType.TEXTO, document_type_code="contactos",
    )
    metadata_service.add_field_definition(
        "p1", schema.id, "promedio_minimo", "Promedio mínimo", FieldDataType.TEXTO,
        document_type_code="requisitos_admision",
    )

    applicable = metadata_service.list_applicable_fields("p1", "contactos")
    assert {f.field_id for f in applicable} == {"idioma", "tel"}


def test_list_source_metadata_values_returns_what_was_set(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")

    values = metadata_service.list_source_metadata_values("p1", source.id)
    assert len(values) == 1
    assert values[0].field_id == "topic"
    assert values[0].value == "becas"


def test_list_source_metadata_values_is_empty_for_a_source_without_values(services):
    metadata_service, document_service = services
    metadata_service.create_schema("p1")
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    assert metadata_service.list_source_metadata_values("p1", source.id) == []


# ---------- historial de cambios (ítem 5 de la evaluación de madurez
# post-8-etapas) ----------

def test_first_assignment_is_recorded_with_no_previous_value(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")

    history = metadata_service.list_value_history("p1", source.id)
    assert len(history) == 1
    assert history[0].field_id == "topic"
    assert history[0].previous_value is None
    assert history[0].new_value == "becas"


def test_changing_the_value_appends_a_new_history_entry_most_recent_first(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "admisiones")

    history = metadata_service.list_value_history("p1", source.id)
    assert len(history) == 2
    assert history[0].previous_value == "becas"
    assert history[0].new_value == "admisiones"
    assert history[1].previous_value is None
    assert history[1].new_value == "becas"
    # el valor vigente sigue siendo upsert -- una sola fila, no dos
    values = metadata_service.list_source_metadata_values("p1", source.id)
    assert len(values) == 1
    assert values[0].value == "admisiones"


def test_saving_the_same_value_again_does_not_add_history_noise(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")

    assert len(metadata_service.list_value_history("p1", source.id)) == 1


def test_history_can_be_filtered_by_field_id(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)
    metadata_service.add_field_definition("p1", schema.id, "audience", "Audiencia", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)

    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "topic", "becas")
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "audience", "estudiantes")

    topic_history = metadata_service.list_value_history("p1", source.id, field_id="topic")
    assert len(topic_history) == 1
    assert topic_history[0].field_id == "topic"


def test_history_is_empty_for_a_source_without_any_value_set(services):
    metadata_service, document_service = services
    metadata_service.create_schema("p1")
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    assert metadata_service.list_value_history("p1", source.id) == []


# ---------- edición de campos ----------

def test_update_field_definition_changes_display_name_and_flags(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)

    updated = metadata_service.update_field_definition(
        "p1", schema.id, "topic", "Tema (editado)", required=True,
    )
    assert updated.display_name == "Tema (editado)"
    assert updated.required is True
    # field_id y data_type no cambian aunque se edite
    assert updated.field_id == "topic"
    assert updated.data_type == FieldDataType.TEXTO


def test_update_field_definition_changes_document_type_code(services):
    # Ronda 5 (video 2, hallazgo real de usuario): duda sobre si
    # "Tipo de documento" y "Obligatorio" realmente se pueden corregir
    # desde "Editar campo" -- se confirma aquí que sí, sin depender de
    # una lectura visual de la interfaz.
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "topic", "Tema", FieldDataType.TEXTO)

    updated = metadata_service.update_field_definition(
        "p1", schema.id, "topic", "Tema", document_type_code="contactos",
    )
    assert updated.document_type_code == "contactos"

    cleared = metadata_service.update_field_definition("p1", schema.id, "topic", "Tema")
    assert cleared.document_type_code is None


def test_update_field_definition_changes_catalog_id_for_catalog_backed_field(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    other_catalog = metadata_service.create_catalog("p1", "Carreras")
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.SELECCION_UNICA, catalog_id=catalog.id,
    )

    updated = metadata_service.update_field_definition(
        "p1", schema.id, "campus_id", "Plantel", catalog_id=other_catalog.id,
    )
    assert updated.catalog_id == other_catalog.id


def test_update_field_definition_missing_field_raises(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    with pytest.raises(FieldDefinitionNotFoundError):
        metadata_service.update_field_definition("p1", schema.id, "no-existe", "X")


def test_update_field_definition_still_requires_catalog_for_catalog_types(services):
    # Antes de CatalogRequiredForFieldTypeError, este caso lo detectaba
    # el model_validator de FieldDefinition y lanzaba
    # pydantic.ValidationError (que también es ValueError) -- ahora lo
    # detecta el comando primero, con un error de dominio propio (ver
    # test_update_field_to_catalog_backed_type_without_catalog_id_raises_clear_domain_error
    # para la prueba dedicada al mensaje/tipo exacto).
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    with pytest.raises(CatalogRequiredForFieldTypeError):
        metadata_service.update_field_definition("p1", schema.id, "campus_id", "Plantel", catalog_id=None)


# ---------- gestión de catálogos ----------

def test_list_catalogs_returns_all_catalogs_of_project(services):
    metadata_service, _ = services
    metadata_service.create_catalog("p1", "Planteles")
    metadata_service.create_catalog("p1", "Programas")
    metadata_service.create_catalog("p2", "Otro proyecto")

    names = {c.name for c in metadata_service.list_catalogs("p1")}
    assert names == {"Planteles", "Programas"}


def test_update_catalog_renames_it(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    updated = metadata_service.update_catalog("p1", catalog.id, "Planteles y campus")
    assert updated.id == catalog.id
    assert updated.name == "Planteles y campus"


def test_delete_catalog_blocked_when_referenced_by_field(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    with pytest.raises(CatalogInUseError):
        metadata_service.delete_catalog("p1", catalog.id)


def test_delete_catalog_succeeds_when_unused(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Sin uso")
    metadata_service.delete_catalog("p1", catalog.id)
    assert metadata_service.list_catalogs("p1") == []


def test_delete_catalog_missing_raises(services):
    metadata_service, _ = services
    with pytest.raises(CatalogNotFoundError):
        metadata_service.delete_catalog("p1", "no-existe")


# ---------- gestión de entradas de catálogo ----------

def test_update_catalog_entry_renames_label(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")

    updated = metadata_service.update_catalog_entry("p1", catalog.id, entry.id, "Mérida, Yucatán")
    assert updated.value_code == "MERIDA"
    assert updated.label == "Mérida, Yucatán"


def test_update_catalog_entry_missing_raises(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    with pytest.raises(CatalogEntryNotFoundError):
        metadata_service.update_catalog_entry("p1", catalog.id, "no-existe", "X")


# ---------- editar código de entrada de catálogo (Ronda 3, punto 13) ----------

def test_update_catalog_entry_can_change_value_code_when_unused(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MRIDA", "Mérida")  # typo intencional

    updated = metadata_service.update_catalog_entry(
        "p1", catalog.id, entry.id, "Mérida", value_code="MERIDA",
    )
    assert updated.value_code == "MERIDA"
    assert updated.label == "Mérida"


def test_update_catalog_entry_blocks_value_code_change_when_in_use(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MRIDA", "Mérida")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus_id", "MRIDA")

    with pytest.raises(CatalogEntryInUseError):
        metadata_service.update_catalog_entry("p1", catalog.id, entry.id, "Mérida", value_code="MERIDA")
    # el bloqueo no debe afectar la etiqueta tampoco -- todo o nada
    assert metadata_service.list_catalog_entries("p1", catalog.id)[0].label == "Mérida"


def test_update_catalog_entry_label_only_ignores_in_use_check(services):
    # Cambiar solo la etiqueta (sin tocar value_code) sigue funcionando
    # igual que antes, incluso si la entrada ya está en uso -- el
    # bloqueo es específicamente sobre el código, no sobre la etiqueta.
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus_id", "MERIDA")

    updated = metadata_service.update_catalog_entry("p1", catalog.id, entry.id, "Mérida, Yucatán")
    assert updated.value_code == "MERIDA"
    assert updated.label == "Mérida, Yucatán"


def test_delete_catalog_entry_blocked_when_value_is_in_use(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    metadata_service.add_field_definition(
        "p1", schema.id, "campus_id", "Plantel", FieldDataType.CATALOGO_JERARQUICO, catalog_id=catalog.id,
    )
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "campus_id", "MERIDA")

    with pytest.raises(CatalogEntryInUseError):
        metadata_service.delete_catalog_entry("p1", catalog.id, entry.id)


def test_delete_catalog_entry_succeeds_when_unused(services):
    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    entry = metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")

    metadata_service.delete_catalog_entry("p1", catalog.id, entry.id)
    assert metadata_service.list_catalog_entries("p1", catalog.id) == []


# ---------- eliminar campo (punto 11 de Validacion_observaciones_RAG_STUDIO.md) ----------

def test_delete_field_succeeds_when_never_used(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "tel", "Teléfono", FieldDataType.TEXTO)

    metadata_service.delete_field_definition("p1", schema.id, "tel")

    _, fields = metadata_service.get_schema("p1")
    assert fields == []


def test_delete_field_blocked_when_source_has_value(services):
    metadata_service, document_service = services
    schema = metadata_service.create_schema("p1")
    metadata_service.add_field_definition("p1", schema.id, "tel", "Teléfono", FieldDataType.TEXTO)
    source = document_service.register_source("p1", "Ficha", SourceType.PDF)
    metadata_service.set_source_metadata_value("p1", schema.id, source.id, "tel", "9999999999")

    with pytest.raises(FieldInUseError):
        metadata_service.delete_field_definition("p1", schema.id, "tel")

    # el campo sigue existiendo -- el bloqueo no debe borrarlo a medias
    _, fields = metadata_service.get_schema("p1")
    assert [f.field_id for f in fields] == ["tel"]


def test_delete_field_missing_raises(services):
    metadata_service, _ = services
    schema = metadata_service.create_schema("p1")
    with pytest.raises(FieldDefinitionNotFoundError):
        metadata_service.delete_field_definition("p1", schema.id, "no-existe")


def test_update_catalog_entry_to_a_code_used_by_another_entry_gives_clear_error(services):
    """Ronda 88 (auditoría): antes terminaba en "UNIQUE constraint failed"."""
    from domain.metadata.exceptions import DuplicateCatalogEntryError

    metadata_service, _ = services
    catalog = metadata_service.create_catalog("p1", "Planteles")
    metadata_service.add_catalog_entry("p1", catalog.id, "MERIDA", "Mérida")
    otra = metadata_service.add_catalog_entry("p1", catalog.id, "CANCUN", "Cancún")
    with pytest.raises(DuplicateCatalogEntryError):
        metadata_service.update_catalog_entry("p1", catalog.id, otra.id, "Cancún", value_code="MERIDA")
