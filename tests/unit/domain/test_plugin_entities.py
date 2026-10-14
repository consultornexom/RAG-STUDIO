"""Pruebas unitarias de las entidades del contexto Complementos (Etapa 8)."""
import pytest
from pydantic import ValidationError

from domain.plugins.entities import Plugin, PluginKind, credential_key, is_sensitive_config_key


def test_plugin_kind_has_the_four_values_from_the_master_document():
    values = {kind.value for kind in PluginKind}
    assert values == {"plantilla", "proveedor", "importador", "evaluador"}


def test_only_plantilla_does_not_require_entry_point():
    for kind in PluginKind:
        plugin = Plugin(kind=kind, code="x", name="x")
        if kind == PluginKind.PLANTILLA:
            assert plugin.requires_entry_point is False
        else:
            assert plugin.requires_entry_point is True


def test_code_cannot_be_blank():
    with pytest.raises(ValidationError):
        Plugin(kind=PluginKind.PLANTILLA, code="   ", name="x")


def test_entry_point_must_follow_module_colon_class_format():
    with pytest.raises(ValidationError):
        Plugin(kind=PluginKind.PROVEEDOR, code="x", name="x", entry_point="sin_dos_puntos")


def test_entry_point_blank_string_is_normalized_to_none():
    plugin = Plugin(kind=PluginKind.PLANTILLA, code="x", name="x", entry_point="   ")
    assert plugin.entry_point is None


def test_kind_coerces_from_plain_string_like_the_rest_of_the_project():
    plugin = Plugin(kind="proveedor", code="x", name="x", entry_point="a.b:C")
    assert plugin.kind == PluginKind.PROVEEDOR


# ---------- is_sensitive_config_key / credential_key (ítem 2 de la segunda evaluación de madurez) ----------

@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "apiKey", "secret", "access_token", "password", "db_credential", "contraseña"],
)
def test_is_sensitive_config_key_matches_common_secret_field_names(key):
    assert is_sensitive_config_key(key) is True


@pytest.mark.parametrize("key", ["modelo", "region", "timeout_ms", "dimensiones", "url"])
def test_is_sensitive_config_key_does_not_match_ordinary_fields(key):
    assert is_sensitive_config_key(key) is False


def test_credential_key_is_stable_and_namespaced_by_plugin_code():
    assert credential_key("openai", "api_key") == "plugin:openai:api_key"
    assert credential_key("openai", "api_key") != credential_key("otro_proveedor", "api_key")
