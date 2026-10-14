"""Pruebas de integración reales (SQLite vía Alembic, línea GLOBAL --
`application.db`, no `project.db`) del repositorio del contexto
Complementos (Etapa 8)."""
from domain.plugins.entities import Plugin, PluginKind
from infrastructure.database.plugin_repositories import SqlAlchemyPluginRepository
from infrastructure.filesystem.paths import InstallationPaths


def _paths(tmp_path):
    paths = InstallationPaths(tmp_path / "agent_studio")
    paths.ensure_installation_layout()
    return paths


def test_plugin_round_trip_preserves_all_fields(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    plugin = Plugin(
        kind=PluginKind.PROVEEDOR, code="openai_embeddings", name="OpenAI Embeddings",
        description="Proveedor externo de ejemplo", version="1.2.3",
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
        config={"api_key_env": "OPENAI_API_KEY"},
    )
    repo.save(plugin)

    fetched = repo.get(plugin.id)
    assert fetched is not None
    assert fetched.kind == PluginKind.PROVEEDOR
    assert fetched.code == "openai_embeddings"
    assert fetched.description == "Proveedor externo de ejemplo"
    assert fetched.version == "1.2.3"
    assert fetched.entry_point == "infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider"
    assert fetched.config == {"api_key_env": "OPENAI_API_KEY"}
    assert fetched.enabled is True


def test_plugin_save_upserts_by_id(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    plugin = Plugin(kind=PluginKind.PLANTILLA, code="t1", name="T1")
    repo.save(plugin)
    updated = plugin.model_copy(update={"enabled": False})
    repo.save(updated)

    fetched = repo.get(plugin.id)
    assert fetched.enabled is False
    assert len(repo.list_all()) == 1


def test_get_by_code_is_scoped_by_kind(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    repo.save(Plugin(kind=PluginKind.PLANTILLA, code="mismo_codigo", name="A"))
    repo.save(Plugin(
        kind=PluginKind.IMPORTADOR, code="mismo_codigo", name="B",
        entry_point="infrastructure.extraction.text_extractors:TxtExtractor",
    ))
    assert repo.get_by_code(PluginKind.PLANTILLA, "mismo_codigo").name == "A"
    assert repo.get_by_code(PluginKind.IMPORTADOR, "mismo_codigo").name == "B"
    assert repo.get_by_code(PluginKind.PROVEEDOR, "mismo_codigo") is None


def test_list_by_kind_only_returns_that_kind(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    repo.save(Plugin(kind=PluginKind.PLANTILLA, code="t1", name="T1"))
    repo.save(Plugin(kind=PluginKind.PLANTILLA, code="t2", name="T2"))
    repo.save(Plugin(
        kind=PluginKind.PROVEEDOR, code="p1", name="P1",
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    ))
    plantillas = repo.list_by_kind(PluginKind.PLANTILLA)
    assert {p.code for p in plantillas} == {"t1", "t2"}
    assert [p.code for p in repo.list_by_kind(PluginKind.PROVEEDOR)] == ["p1"]


def test_list_all_is_empty_for_a_fresh_installation(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    assert repo.list_all() == []


def test_delete_removes_the_plugin(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    plugin = Plugin(kind=PluginKind.PLANTILLA, code="t1", name="T1")
    repo.save(plugin)

    repo.delete(plugin.id)

    assert repo.get(plugin.id) is None
    assert repo.list_all() == []


def test_delete_is_idempotent_for_an_unknown_id(tmp_path):
    repo = SqlAlchemyPluginRepository(_paths(tmp_path))
    repo.delete("no-existe")  # no debe lanzar
