"""Prueba de punta a punta del contexto Ingesta sobre un AppContext
real (bootstrap completo, SQLite real, archivo real en disco) — mismo
patrón que las pruebas de humo de Etapa 1/2, pero para Etapa 3."""
from domain.documents.entities import SourceType
from domain.ingestion.entities import FragmentationStrategy


def test_extract_and_fragment_real_txt_source_through_app_context(app_context, tmp_path):
    source_path = tmp_path / "reglamento.md"
    source_path.write_text(
        "# Admisión\nRequisitos de admisión para el ciclo escolar.\n\n"
        "# Bajas\nProceso para tramitar una baja temporal.\n",
        encoding="utf-8",
    )

    project = app_context.project_service.create_project("Piloto ingesta")
    source = app_context.document_service.register_source(
        project.id, "Reglamento", SourceType.MARKDOWN, location=str(source_path),
    )

    record = app_context.ingestion_service.extract_source_text(project.id, source.id)
    assert "Admisión" in record.text

    app_context.ingestion_service.set_fragmentation_policy(
        project.id, "reglamento", strategy=FragmentationStrategy.POR_ENCABEZADO,
    )
    chunks = app_context.ingestion_service.fragment_source(
        project.id, source.id, document_type_code="reglamento",
    )

    assert [c.section_title for c in chunks] == ["Admisión", "Bajas"]
    listed = app_context.ingestion_service.list_chunks(project.id, source.id)
    assert len(listed) == 2


def test_fragmentation_inherits_metadata_through_real_metadata_service(app_context, tmp_path):
    source_path = tmp_path / "aviso.txt"
    source_path.write_text("Aviso importante para todos los planteles.", encoding="utf-8")

    project = app_context.project_service.create_project("Piloto ingesta 2")
    source = app_context.document_service.register_source(
        project.id, "Aviso", SourceType.TXT, location=str(source_path),
    )

    schema = app_context.metadata_service.create_schema(project.id)
    app_context.metadata_service.add_field_definition(
        project.id, schema.id, "campus", "Plantel", "texto", inherited_by_chunks=True,
    )
    app_context.metadata_service.set_source_metadata_value(project.id, schema.id, source.id, "campus", "MERIDA")

    app_context.ingestion_service.extract_source_text(project.id, source.id)
    app_context.ingestion_service.set_fragmentation_policy(
        project.id, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO,
    )
    chunks = app_context.ingestion_service.fragment_source(project.id, source.id, schema_id=schema.id)

    assert len(chunks) == 1
    assert chunks[0].inherited_metadata == {"campus": "MERIDA"}
