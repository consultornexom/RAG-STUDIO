"""Pruebas unitarias de PluginService (fachada de application para el
contexto Complementos, Etapa 8) -- registro, activar/desactivar,
listar y validar."""
import pytest

from domain.plugins.entities import CREDENTIAL_STORE_PLACEHOLDER
from domain.plugins.exceptions import DuplicatePluginCodeError, MissingEntryPointError, PluginNotFoundError

from .fakes_plugins import FailingCredentialStore, InMemoryCredentialStore, InMemoryPluginRepository
from application.plugins.service import PluginService


def _make_service(credential_store=None) -> PluginService:
    return PluginService(InMemoryPluginRepository(), credential_store=credential_store)


def test_register_plugin_requires_entry_point_for_proveedor():
    service = _make_service()
    with pytest.raises(MissingEntryPointError):
        service.register_plugin("proveedor", "sin_entry_point", "x")


def test_register_plugin_allows_plantilla_without_entry_point():
    service = _make_service()
    plugin = service.register_plugin("plantilla", "plantilla_educativa", "Plantilla educativa", config={"a": "1"})
    assert plugin.entry_point is None
    assert plugin.config == {"a": "1"}


def test_register_plugin_rejects_duplicate_code_within_the_same_kind():
    service = _make_service()
    service.register_plugin(
        "proveedor", "openai", "OpenAI", entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    with pytest.raises(DuplicatePluginCodeError):
        service.register_plugin(
            "proveedor", "openai", "OpenAI de nuevo",
            entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
        )


def test_register_plugin_allows_same_code_across_different_kinds():
    service = _make_service()
    service.register_plugin(
        "proveedor", "mismo_codigo", "A", entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    plugin = service.register_plugin(
        "importador", "mismo_codigo", "B", entry_point="infrastructure.extraction.text_extractors:TxtExtractor",
    )
    assert plugin.code == "mismo_codigo"


def test_set_plugin_enabled_toggles_without_deleting():
    service = _make_service()
    plugin = service.register_plugin("plantilla", "x", "X")
    updated = service.set_plugin_enabled(plugin.id, False)
    assert updated.enabled is False
    assert service.get_plugin(plugin.id).enabled is False


def test_set_plugin_enabled_raises_for_unknown_plugin():
    service = _make_service()
    with pytest.raises(PluginNotFoundError):
        service.set_plugin_enabled("no-existe", False)


def test_list_plugins_and_list_by_kind():
    service = _make_service()
    service.register_plugin("plantilla", "t1", "T1")
    service.register_plugin(
        "proveedor", "p1", "P1", entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    assert {p.code for p in service.list_plugins()} == {"t1", "p1"}
    assert [p.code for p in service.list_plugins_by_kind("plantilla")] == ["t1"]
    assert [p.code for p in service.list_plugins_by_kind("proveedor")] == ["p1"]


def test_validate_plugin_ok_for_a_real_contract_match():
    service = _make_service()
    plugin = service.register_plugin(
        "proveedor", "p1", "P1", entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    result = service.validate_plugin(plugin.id)
    assert result["ok"] is True


def test_validate_plugin_fails_for_wrong_contract():
    service = _make_service()
    plugin = service.register_plugin(
        "proveedor", "p1", "P1", entry_point="infrastructure.extraction.text_extractors:TxtExtractor",
    )
    result = service.validate_plugin(plugin.id)
    assert result["ok"] is False


def test_validate_plugin_raises_for_unknown_plugin():
    service = _make_service()
    with pytest.raises(PluginNotFoundError):
        service.validate_plugin("no-existe")


def test_get_plugin_returns_none_for_unknown_id():
    service = _make_service()
    assert service.get_plugin("no-existe") is None


# ---------- CredentialStore (ítem 2 de la segunda evaluación de madurez) ----------

def test_register_plugin_without_credential_store_keeps_config_in_plain_text():
    service = _make_service(credential_store=None)
    plugin = service.register_plugin(
        "proveedor", "openai", "OpenAI", config={"api_key": "sk-secreto"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    # Sin almacén configurado, el comportamiento es exactamente el de
    # antes de este ítem: config se guarda tal cual llegó.
    assert plugin.config == {"api_key": "sk-secreto"}


def test_register_plugin_externalizes_sensitive_keys_to_credential_store():
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    plugin = service.register_plugin(
        "proveedor", "openai", "OpenAI",
        config={"api_key": "sk-secreto", "modelo": "text-embedding-3"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    # api_key (sensible) sale del config persistido y queda un marcador;
    # modelo (no sensible) se queda tal cual.
    assert plugin.config["api_key"] == CREDENTIAL_STORE_PLACEHOLDER
    assert plugin.config["modelo"] == "text-embedding-3"
    assert store.get_secret("plugin:openai:api_key") == "sk-secreto"


def test_resolve_plugin_config_recovers_the_real_secret_value():
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    plugin = service.register_plugin(
        "proveedor", "openai", "OpenAI", config={"api_key": "sk-secreto"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    resolved = service.resolve_plugin_config(plugin)
    assert resolved["api_key"] == "sk-secreto"


def test_register_plugin_falls_back_to_plain_text_when_credential_store_fails():
    service = _make_service(credential_store=FailingCredentialStore())
    # No debe romper el registro del complemento: mismo criterio de
    # degradación segura que TokenizerError/EmbeddingProviderError.
    plugin = service.register_plugin(
        "proveedor", "openai", "OpenAI", config={"api_key": "sk-secreto"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    assert plugin.config["api_key"] == "sk-secreto"


def test_non_sensitive_keys_are_never_sent_to_credential_store():
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    service.register_plugin(
        "proveedor", "openai", "OpenAI", config={"modelo": "text-embedding-3", "region": "us-east-1"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    assert store.set_calls == []


def test_resolve_plugin_config_without_credential_store_returns_config_unchanged():
    service = _make_service(credential_store=None)
    plugin = service.register_plugin(
        "proveedor", "openai", "OpenAI", config={"modelo": "text-embedding-3"},
        entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    assert service.resolve_plugin_config(plugin) == {"modelo": "text-embedding-3"}


# ---------- editar / desregistrar (Ronda 4, punto 3) ----------

def test_update_plugin_edits_descriptive_fields_but_not_code_or_kind():
    service = _make_service()
    plugin = service.register_plugin("plantilla", "p1", "Original", description="vieja")
    updated = service.update_plugin(
        plugin.id, "Nuevo nombre", description="nueva", version="0.2.0", config={"a": "1"},
    )
    assert updated.name == "Nuevo nombre"
    assert updated.description == "nueva"
    assert updated.version == "0.2.0"
    assert updated.config == {"a": "1"}
    assert updated.code == "p1"
    assert updated.kind.value == "plantilla"


def test_update_plugin_raises_for_unknown_plugin():
    service = _make_service()
    with pytest.raises(PluginNotFoundError):
        service.update_plugin("no-existe", "X")


def test_update_plugin_still_requires_entry_point_for_proveedor():
    service = _make_service()
    plugin = service.register_plugin(
        "proveedor", "p1", "P1", entry_point="infrastructure.embeddings.fastembed_provider:FastEmbedEmbeddingProvider",
    )
    with pytest.raises(MissingEntryPointError):
        service.update_plugin(plugin.id, "P1", entry_point=None)


def test_update_plugin_externalizes_a_newly_added_sensitive_key():
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    plugin = service.register_plugin("plantilla", "p1", "P1", config={"modelo": "x"})
    updated = service.update_plugin(plugin.id, "P1", config={"modelo": "x", "api_key": "sk-nueva"})
    assert updated.config["api_key"] == CREDENTIAL_STORE_PLACEHOLDER
    assert store.get_secret("plugin:p1:api_key") == "sk-nueva"


def test_update_plugin_does_not_overwrite_the_real_secret_when_placeholder_is_resent():
    """Si el formulario de edición precarga el config guardado (que ya
    trae el marcador en los campos sensibles) y la persona no lo toca,
    reenviar ese config sin cambios no debe sobrescribir el secreto real
    en el almacén con el texto del marcador."""
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    plugin = service.register_plugin("plantilla", "p1", "P1", config={"api_key": "sk-real"})
    assert plugin.config["api_key"] == CREDENTIAL_STORE_PLACEHOLDER

    updated = service.update_plugin(plugin.id, "P1 editado", config=dict(plugin.config))

    assert updated.config["api_key"] == CREDENTIAL_STORE_PLACEHOLDER
    assert store.get_secret("plugin:p1:api_key") == "sk-real"


def test_unregister_plugin_removes_it():
    service = _make_service()
    plugin = service.register_plugin("plantilla", "p1", "P1")
    service.unregister_plugin(plugin.id)
    assert service.get_plugin(plugin.id) is None


def test_unregister_plugin_raises_for_unknown_plugin():
    service = _make_service()
    with pytest.raises(PluginNotFoundError):
        service.unregister_plugin("no-existe")


def test_unregister_plugin_cleans_up_externalized_secrets():
    store = InMemoryCredentialStore()
    service = _make_service(credential_store=store)
    plugin = service.register_plugin("plantilla", "p1", "P1", config={"api_key": "sk-secreto"})
    assert store.get_secret("plugin:p1:api_key") == "sk-secreto"

    service.unregister_plugin(plugin.id)

    assert store.get_secret("plugin:p1:api_key") is None
