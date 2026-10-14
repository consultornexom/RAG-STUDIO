import pytest

from application.documents.service import DocumentService
from domain.documents.entities import AccessLevel, SourceType, SourceValidationStatus
from domain.documents.exceptions import DuplicateSourceError, SourceNotFoundError, SourceStructuralFieldsLockedError
from domain.ingestion.entities import ExtractionRecord

from .fakes_documents import InMemorySourceFileStore, InMemorySourceRepository
from .fakes_ingestion import InMemoryExtractionRepository


@pytest.fixture
def service():
    return DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository())


@pytest.fixture
def service_and_extraction_repository():
    # Igual que `service`, pero exponiendo también el
    # InMemoryExtractionRepository para poder simular "esta fuente ya
    # tiene texto extraído" en las pruebas que verifican el bloqueo de
    # location/source_type (ver UpdateSourceDetails).
    extraction_repository = InMemoryExtractionRepository()
    return DocumentService(InMemorySourceRepository(), extraction_repository), extraction_repository


def test_register_source(service):
    source = service.register_source("p1", "Reglamento", SourceType.PDF)
    assert source.project_id == "p1"
    assert source.validation_status == SourceValidationStatus.BORRADOR


def test_duplicate_content_hash_is_rejected(service):
    service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    with pytest.raises(DuplicateSourceError):
        service.register_source("p1", "Copia idéntica", SourceType.PDF, content_hash="hash-1")


def test_supersede_marks_old_source_as_sustituido(service):
    old = service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    old = service.update_validation_status(
        "p1", old.id, SourceValidationStatus.EN_REVISION
    )
    old = service.update_validation_status("p1", old.id, SourceValidationStatus.VALIDADO)

    new = service.register_source(
        "p1", "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=old.id
    )
    refreshed_old = service.get_source("p1", old.id)
    assert refreshed_old.validation_status == SourceValidationStatus.SUSTITUIDO
    assert new.supersedes_source_id == old.id


def test_supersede_with_a_nonexistent_id_logs_a_warning_instead_of_failing_silently(service, caplog):
    # Auditoría profunda (ronda posterior a la 76, ver bitácora):
    # antes de esta ronda, un supersedes_source_id que no resolvía a
    # ninguna fuente real (id mal escrito, de otro proyecto, o ya
    # borrada) se ignoraba sin dejar ningún rastro -- a diferencia de
    # _try_copy_original, que sí registra sus propios fallos. El
    # registro de la fuente nueva no debe fallar (es la fuente nueva
    # la que se está creando, no la vieja), pero ahora queda una
    # advertencia clara en el log técnico.
    with caplog.at_level("WARNING"):
        new = service.register_source(
            "p1", "Reglamento v2", SourceType.PDF, supersedes_source_id="id-que-no-existe",
        )
    assert new.supersedes_source_id == "id-que-no-existe"
    assert any("no existe ninguna fuente" in record.message for record in caplog.records)


def test_get_source_lineage_with_a_single_source_returns_only_itself(service):
    solo = service.register_source("p1", "Reglamento único", SourceType.PDF)

    lineage = service.get_source_lineage("p1", solo.id)

    assert [s.id for s in lineage] == [solo.id]


def test_get_source_lineage_walks_backward_from_the_newest_version(service):
    v1 = service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    v2 = service.register_source(
        "p1", "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=v1.id,
    )

    lineage = service.get_source_lineage("p1", v2.id)

    assert [s.id for s in lineage] == [v1.id, v2.id]


def test_get_source_lineage_walks_forward_from_the_oldest_version(service):
    # Mismo escenario que la prueba anterior, pero pidiendo el linaje
    # desde la fuente MÁS VIEJA -- antes de esta pista, ui/sources/
    # panel.py solo sabía caminar hacia atrás; esta prueba cubre
    # justamente el sentido que faltaba.
    v1 = service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    v2 = service.register_source(
        "p1", "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=v1.id,
    )

    lineage = service.get_source_lineage("p1", v1.id)

    assert [s.id for s in lineage] == [v1.id, v2.id]


def test_get_source_lineage_with_three_versions_returns_the_full_chain_oldest_first(service):
    v1 = service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    v2 = service.register_source(
        "p1", "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=v1.id,
    )
    v3 = service.register_source(
        "p1", "Reglamento v3", SourceType.PDF, content_hash="hash-3", supersedes_source_id=v2.id,
    )

    # Pedida desde el eslabón intermedio -- debe traer la cadena
    # completa en las tres direcciones posibles (atrás, ella misma,
    # adelante), no solo lo que está de un lado.
    lineage = service.get_source_lineage("p1", v2.id)

    assert [s.id for s in lineage] == [v1.id, v2.id, v3.id]


def test_get_source_lineage_scopes_by_project_id(service):
    other_project_source = service.register_source("p2", "Fuente de otro proyecto", SourceType.PDF)
    this_project_source = service.register_source("p1", "Reglamento", SourceType.PDF)

    lineage = service.get_source_lineage("p1", this_project_source.id)

    assert [s.id for s in lineage] == [this_project_source.id]
    assert other_project_source.id not in [s.id for s in lineage]


def test_get_source_lineage_missing_source_raises(service):
    with pytest.raises(SourceNotFoundError):
        service.get_source_lineage("p1", "no-existe")


def test_export_source_lineage_as_csv_includes_every_version_in_order(service):
    v1 = service.register_source("p1", "Reglamento v1", SourceType.PDF, content_hash="hash-1")
    v2 = service.register_source(
        "p1", "Reglamento v2", SourceType.PDF, content_hash="hash-2", supersedes_source_id=v1.id,
    )

    csv_text = service.export_source_lineage_as_csv("p1", v2.id)
    lines = csv_text.strip().splitlines()

    assert lines[0] == "orden,id,titulo,estado_validacion,vigente_desde,vigente_hasta,content_hash,sustituye_a"
    assert len(lines) == 3  # encabezado + 2 versiones
    assert f"1,{v1.id},Reglamento v1" in lines[1]
    assert f"2,{v2.id},Reglamento v2" in lines[2]
    assert lines[2].strip().endswith(v1.id)  # "sustituye_a" es la columna final


def test_get_missing_source_raises(service):
    with pytest.raises(SourceNotFoundError):
        service.get_source("p1", "no-existe")


def test_list_sources_scoped_by_project(service):
    service.register_source("p1", "Fuente 1", SourceType.PDF)
    service.register_source("p2", "Fuente 2", SourceType.PDF)
    assert len(service.list_sources("p1")) == 1
    assert len(service.list_sources("p2")) == 1


# ---------- update_source_details (hallazgo real de validación visual) ----------

def test_update_source_details_edits_descriptive_fields_freely(service):
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/x.pdf")
    updated = service.update_source_details(
        "p1", source.id, "Ficha corregida", "Rectoría", AccessLevel.CONFIDENCIAL,
        source.location, source.source_type,
    )
    assert updated.title == "Ficha corregida"
    assert updated.owner_area == "Rectoría"
    assert updated.access_level == AccessLevel.CONFIDENCIAL
    # los estructurales no cambiaron, así que no hay bloqueo posible
    assert updated.location == "/x.pdf"


def test_update_source_details_edits_language(service):
    # Análisis de brechas dominio/UI a raíz de la nota de "valor
    # múltiple" del Manual del Usuario, sección 6.1: language existe en
    # domain desde siempre (default "es"), pero antes de este hallazgo
    # no había ninguna forma de corregirlo después de registrar la
    # fuente -- ni siquiera a nivel de application (update_source_details
    # ni recibía el parámetro).
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/x.pdf")
    assert source.language == "es"
    updated = service.update_source_details(
        "p1", source.id, source.title, source.owner_area, source.access_level,
        source.location, source.source_type, language="en",
    )
    assert updated.language == "en"
    assert service.get_source("p1", source.id).language == "en"


def test_update_source_details_allows_location_change_without_extraction(service):
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/viejo.pdf")
    assert service.has_extraction("p1", source.id) is False
    updated = service.update_source_details(
        "p1", source.id, source.title, source.owner_area, source.access_level,
        "/nuevo.pdf", source.source_type,
    )
    assert updated.location == "/nuevo.pdf"


def test_update_source_details_blocks_location_change_once_extracted(service_and_extraction_repository):
    service, extraction_repository = service_and_extraction_repository
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/viejo.pdf")
    extraction_repository.save(ExtractionRecord(project_id="p1", source_id=source.id, text="contenido real"))

    assert service.has_extraction("p1", source.id) is True
    with pytest.raises(SourceStructuralFieldsLockedError):
        service.update_source_details(
            "p1", source.id, source.title, source.owner_area, source.access_level,
            "/nuevo.pdf", source.source_type,
        )
    # el registro no debe haber cambiado tras el intento bloqueado
    assert service.get_source("p1", source.id).location == "/viejo.pdf"


def test_update_source_details_blocks_source_type_change_once_extracted(service_and_extraction_repository):
    service, extraction_repository = service_and_extraction_repository
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/x.pdf")
    extraction_repository.save(ExtractionRecord(project_id="p1", source_id=source.id, text="contenido real"))

    with pytest.raises(SourceStructuralFieldsLockedError):
        service.update_source_details(
            "p1", source.id, source.title, source.owner_area, source.access_level,
            source.location, SourceType.DOCX,
        )


def test_update_source_details_allows_descriptive_edit_even_after_extraction(service_and_extraction_repository):
    # El bloqueo es solo para location/source_type -- los campos
    # descriptivos siguen editables aunque ya haya extracción, porque
    # nada depende de ellos.
    service, extraction_repository = service_and_extraction_repository
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/x.pdf")
    extraction_repository.save(ExtractionRecord(project_id="p1", source_id=source.id, text="contenido real"))

    updated = service.update_source_details(
        "p1", source.id, "Ficha revisada", source.owner_area, source.access_level,
        source.location, source.source_type,
    )
    assert updated.title == "Ficha revisada"


def test_update_source_details_missing_source_raises(service):
    with pytest.raises(SourceNotFoundError):
        service.update_source_details(
            "p1", "no-existe", "Título", None, AccessLevel.INTERNO, "/x.pdf", SourceType.PDF,
        )


# ---------- copiar el archivo original al proyecto (ítem 4 de la
# evaluación de madurez post-8-etapas) ----------

def test_register_source_copies_original_when_file_store_configured():
    file_store = InMemorySourceFileStore()
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)

    source = service.register_source("p1", "Reglamento", SourceType.PDF, location="/externo/reglamento.pdf")

    assert source.original_copy_path == f"/fake-store/p1/sources/original/{source.id}"
    assert file_store.calls == [("p1", source.id, "/externo/reglamento.pdf")]
    # y queda persistido, no solo en el objeto devuelto en memoria
    assert service.get_source("p1", source.id).original_copy_path == source.original_copy_path


def test_register_source_skips_copy_without_file_store(service):
    # `service` (fixture de arriba) no recibe file_store -- mismo
    # comportamiento de siempre, sin ningún intento de copia.
    source = service.register_source("p1", "Reglamento", SourceType.PDF, location="/externo/reglamento.pdf")
    assert source.original_copy_path is None


def test_register_source_skips_copy_for_non_file_source_types():
    file_store = InMemorySourceFileStore()
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)

    source = service.register_source("p1", "API externa", SourceType.API, location="https://ejemplo.mx/api")

    assert source.original_copy_path is None
    assert file_store.calls == []


def test_register_source_skips_copy_when_location_is_empty():
    file_store = InMemorySourceFileStore()
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)

    source = service.register_source("p1", "Sin ubicación todavía", SourceType.PDF)

    assert source.original_copy_path is None
    assert file_store.calls == []


def test_register_source_survives_copy_failure():
    # La ruta no existe (no está en el sistema de archivos real
    # tampoco, pero el fake simula el mismo fallo): el registro debe
    # completarse igual, sin propagar el error de copia.
    file_store = InMemorySourceFileStore(missing_paths={"/no-existe.pdf"})
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)

    source = service.register_source("p1", "Reglamento", SourceType.PDF, location="/no-existe.pdf")

    assert source.original_copy_path is None
    assert source.title == "Reglamento"  # el registro sí se completó


def test_register_source_logs_warning_on_copy_failure(caplog):
    # Ítem de la tercera ronda de madurez: el fallo silencioso al copiar
    # el archivo original ahora deja rastro en el log técnico, sin
    # cambiar el comportamiento (el registro sigue completándose igual).
    file_store = InMemorySourceFileStore(missing_paths={"/no-existe.pdf"})
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)

    with caplog.at_level("WARNING"):
        source = service.register_source("p1", "Reglamento", SourceType.PDF, location="/no-existe.pdf")

    assert source.original_copy_path is None
    assert any(record.levelname == "WARNING" for record in caplog.records)
    assert any("no se pudo copiar" in record.getMessage().lower() for record in caplog.records)


def test_update_source_details_recopies_when_location_changes():
    file_store = InMemorySourceFileStore()
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/viejo.pdf")
    first_copy_path = source.original_copy_path

    updated = service.update_source_details(
        "p1", source.id, source.title, source.owner_area, source.access_level,
        "/nuevo.pdf", source.source_type,
    )

    assert updated.location == "/nuevo.pdf"
    assert updated.original_copy_path == first_copy_path  # el fake devuelve la misma ruta por source_id
    assert file_store.calls[-1] == ("p1", source.id, "/nuevo.pdf")


def test_update_source_details_leaves_copy_untouched_when_location_unchanged():
    file_store = InMemorySourceFileStore()
    service = DocumentService(InMemorySourceRepository(), InMemoryExtractionRepository(), file_store=file_store)
    source = service.register_source("p1", "Ficha", SourceType.PDF, location="/x.pdf")
    calls_after_register = list(file_store.calls)

    service.update_source_details(
        "p1", source.id, "Ficha renombrada", source.owner_area, source.access_level,
        source.location, source.source_type,
    )

    # Ningún cambio estructural -- no debe haber una nueva llamada de copia.
    assert file_store.calls == calls_after_register


# ---------- bulk_set_document_type_code (Ronda 4, punto 4a) ----------

def test_bulk_set_document_type_code_updates_all_selected_sources(service):
    a = service.register_source("p1", "A", SourceType.PDF, document_type_code="default")
    b = service.register_source("p1", "B", SourceType.PDF, document_type_code="default")
    c = service.register_source("p1", "C", SourceType.PDF, document_type_code="default")

    result = service.bulk_set_document_type_code("p1", [a.id, b.id], "requisitos_admision")

    assert result.updated_count == 2
    assert result.skipped_count == 0
    assert service.get_source("p1", a.id).document_type_code == "requisitos_admision"
    assert service.get_source("p1", b.id).document_type_code == "requisitos_admision"
    # la que no se incluyó en la selección no se toca
    assert service.get_source("p1", c.id).document_type_code == "default"


def test_bulk_set_document_type_code_skips_unknown_ids_without_aborting(service):
    a = service.register_source("p1", "A", SourceType.PDF, document_type_code="default")

    result = service.bulk_set_document_type_code("p1", [a.id, "no-existe"], "contactos")

    assert result.updated_source_ids == [a.id]
    assert result.skipped_source_ids == ["no-existe"]
    assert service.get_source("p1", a.id).document_type_code == "contactos"


def test_bulk_set_document_type_code_preserves_other_descriptive_fields(service):
    source = service.register_source(
        "p1", "Ficha", SourceType.PDF, owner_area="Rectoría", access_level=AccessLevel.CONFIDENCIAL,
        document_type_code="default",
    )

    service.bulk_set_document_type_code("p1", [source.id], "contactos")

    updated = service.get_source("p1", source.id)
    assert updated.document_type_code == "contactos"
    assert updated.owner_area == "Rectoría"
    assert updated.access_level == AccessLevel.CONFIDENCIAL
    assert updated.title == "Ficha"


def test_bulk_set_document_type_code_empty_selection_is_a_no_op(service):
    result = service.bulk_set_document_type_code("p1", [], "contactos")
    assert result.updated_count == 0
    assert result.skipped_count == 0
