"""Ronda 97 (hallazgo real de NEXOM, AGENTE UDL): campo de varios valores
con catálogo, de punta a punta sobre un AppContext real (SQLite real):
persistencia al cerrar y volver a abrir, herencia a los fragmentos y
carga útil del índice."""
from app.lifecycle import shutdown, start
from application.rag.commands.index_source import _build_payload
from domain.documents.entities import SourceType
from domain.ingestion.entities import FragmentationStrategy


def _proyecto(ctx, tmp_path):
    ruta = tmp_path / "requisitos_ingreso.md"
    ruta.write_text("# Requisitos\nRequisitos de ingreso comunes a los planteles.\n", encoding="utf-8")
    project = ctx.project_service.create_project("UDL multivalor")
    source = ctx.document_service.register_source(project.id, "requisitos_ingreso.md", SourceType.MARKDOWN,
                                                  location=str(ruta))
    meta = ctx.metadata_service
    schema = meta.create_schema(project.id)
    catalog = meta.create_catalog(project.id, "campus_udl")
    meta.add_catalog_entry(project.id, catalog.id, "hilario_medina", "Hilario Medina")
    meta.add_catalog_entry(project.id, catalog.id, "torres_landa", "Torres Landa")
    meta.add_field_definition(project.id, schema.id, "campus", "Campus o plantel", "seleccion_multiple",
                              multiple=True, filterable=True, inherited_by_chunks=True, catalog_id=catalog.id)
    return project.id, schema.id, source.id


def test_valores_multiples_persisten_al_cerrar_y_reabrir(tmp_path):
    base = tmp_path / "inst"
    ctx = start(base_dir=base)
    try:
        pid, sid, src = _proyecto(ctx, tmp_path)
        ctx.metadata_service.set_source_metadata_value(pid, sid, src, "campus", ["hilario_medina"])
        ctx.metadata_service.set_source_metadata_value(pid, sid, src, "campus", ["torres_landa"], mode="agregar")
    finally:
        shutdown(ctx)
    ctx = start(base_dir=base)
    try:
        [valor] = ctx.metadata_service.list_source_metadata_values(pid, src)
        assert valor.value == "hilario_medina|torres_landa"
        ctx.metadata_service.remove_source_metadata_value_item(pid, sid, src, "campus", "hilario_medina")
        [valor] = ctx.metadata_service.list_source_metadata_values(pid, src)
        assert valor.value == "torres_landa"
    finally:
        shutdown(ctx)


def test_los_dos_valores_se_heredan_a_los_fragmentos_y_al_indice(app_context, tmp_path):
    pid, sid, src = _proyecto(app_context, tmp_path)
    app_context.metadata_service.set_source_metadata_value(pid, sid, src, "campus", ["hilario_medina", "torres_landa"])
    app_context.ingestion_service.extract_source_text(pid, src)
    app_context.ingestion_service.set_fragmentation_policy(pid, "default", strategy=FragmentationStrategy.DOCUMENTO_COMPLETO)
    chunks = app_context.ingestion_service.fragment_source(pid, src, schema_id=sid)
    assert chunks and all(c.inherited_metadata == {"campus": "hilario_medina|torres_landa"} for c in chunks)
    assert _build_payload(chunks[0])["meta__campus"] == "hilario_medina|torres_landa"
