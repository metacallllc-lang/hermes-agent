"""Catalog additions must preserve a registered provider's credential contract."""

from types import SimpleNamespace

from hermes_cli import providers as catalog
from providers import get_provider_profile


def test_catalog_provider_keeps_profile_key_names_without_turning_url_vars_into_keys(monkeypatch):
    profile = get_provider_profile("commandcode")
    assert profile is not None
    registered_keys = tuple(v for v in profile.env_vars if not v.endswith(("_BASE_URL", "_URL")))
    info = SimpleNamespace(name="Catalog entry", env=("CATALOG_FIXTURE_API_KEY",),
                           api="https://catalog.example/v1", doc="https://catalog.example/docs")
    monkeypatch.setattr(catalog, "_models_dev_info", lambda name, *args: info if name == "commandcode" else None)
    definition = catalog.resolve_provider_full("commandcode", {}, [])
    assert definition is not None
    assert set(registered_keys).issubset(definition.api_key_env_vars)
    assert "CATALOG_FIXTURE_API_KEY" in definition.api_key_env_vars
    assert not any(v.endswith(("_BASE_URL", "_URL")) for v in definition.api_key_env_vars)
    # Adding a supported key name must not redirect the provider's endpoint.
    assert definition.base_url == info.api
    monkeypatch.delenv("CATALOG_FIXTURE_API_KEY", raising=False)
    monkeypatch.setenv(registered_keys[0], "fixture-existing-profile-key")
    import os
    assert next((os.environ[v] for v in definition.api_key_env_vars if os.environ.get(v)), None) == "fixture-existing-profile-key"


def test_explicit_user_provider_still_owns_its_endpoint_and_key_names(monkeypatch):
    info = SimpleNamespace(name="Catalog entry", env=("CATALOG_FIXTURE_API_KEY",),
                           api="https://catalog.example/v1", doc="https://catalog.example/docs")
    monkeypatch.setattr(catalog, "_models_dev_info", lambda *args: info)
    definition = catalog.resolve_provider_full("commandcode", {"commandcode": {
        "base_url": "https://configured.example/v1", "api_key_env": "CONFIGURED_FIXTURE_API_KEY",
    }}, [])
    assert definition is not None
    assert definition.base_url == "https://configured.example/v1"
    assert definition.api_key_env_vars == ("CONFIGURED_FIXTURE_API_KEY",)
