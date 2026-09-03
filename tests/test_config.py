"""Test isolated, explicitly configured runtime settings."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_default_config(config_factory):
    """Test default configuration values."""
    config = config_factory()
    assert config.osm_use_dev_api is True
    assert config.osm_dev_api_base == "https://api06.dev.openstreetmap.org/api/0.6"
    assert config.osm_api_base == "https://api.openstreetmap.org/api/0.6"
    assert config.default_changeset_comment == "Edited via OSM Edit MCP Server"
    assert config.require_user_confirmation is True
    assert config.rate_limit_per_minute == 60
    assert config.max_changeset_size == 50


def test_current_api_base_url(config_factory):
    """Test API URL selection based on dev/prod setting."""
    config = config_factory()

    # Test development mode
    config.osm_use_dev_api = True
    assert config.current_api_base_url == config.osm_dev_api_base

    # Test production mode
    config.osm_use_dev_api = False
    assert config.current_api_base_url == config.osm_api_base


@pytest.mark.parametrize(
    ("use_dev_api", "legacy_target", "message"),
    [
        (
            True,
            "https://api.openstreetmap.org/api/0.6",
            "production server",
        ),
        (
            False,
            "https://api06.dev.openstreetmap.org/api/0.6",
            "development server",
        ),
    ],
)
def test_known_api_target_cannot_contradict_mode(
    config_factory, use_dev_api, legacy_target, message
):
    with pytest.raises(ValueError, match=message):
        config_factory(
            osm_use_dev_api=use_dev_api,
            osm_api_base_url=legacy_target,
        )


def test_runtime_target_mutation_is_revalidated(config_factory):
    config = config_factory()
    config.osm_api_base_url = "https://api.openstreetmap.org/api/0.6"

    with pytest.raises(ValueError, match="production server"):
        _ = config.current_api_base_url


def test_custom_target_never_enables_dev_only_write_tools(config_factory):
    config = config_factory(
        osm_use_dev_api=True,
        osm_dev_api_base="https://trusted.example/api/0.6",
        osm_allow_custom_api_base=True,
        osm_write_profile="expert",
    )

    assert config.api_environment == "custom"
    assert config.is_development_api is False
    assert config.direct_write_tools_enabled is False
    assert config.current_web_base_url == "https://trusted.example"


def test_custom_target_registration_is_fail_closed():
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("OSM_")
    }
    env.update(
        {
            "OSM_USE_DEV_API": "true",
            "OSM_DEV_API_BASE": "https://trusted.example/api/0.6",
            "OSM_ALLOW_CUSTOM_API_BASE": "true",
            "OSM_WRITE_PROFILE": "expert",
            "USE_KEYRING": "false",
            "ALLOW_PLAINTEXT_TOKEN_FILE": "false",
        }
    )
    code = """
import json
from src.osm_edit_mcp.server import config, mcp
names = sorted(tool.name for tool in mcp._tool_manager.list_tools())
print(json.dumps({"environment": config.api_environment, "names": names}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert payload["environment"] == "custom"
    assert "apply_track_road_edit" not in payload["names"]
    assert "create_osm_node" not in payload["names"]


def test_oauth_config_selection(config_factory):
    """Test OAuth configuration selection based on dev/prod."""
    config = config_factory()

    # Set test values
    config.osm_dev_client_id = "dev_id"
    config.osm_prod_client_id = "prod_id"
    config.osm_dev_client_secret = "dev_secret"
    config.osm_prod_client_secret = "prod_secret"
    config.osm_dev_redirect_uri = "https://dev.example/callback"
    config.osm_prod_redirect_uri = "https://prod.example/callback"
    config.osm_oauth_client_id = "legacy_id"
    config.osm_oauth_client_secret = "legacy_secret"
    config.osm_oauth_redirect_uri = "https://legacy.example/callback"

    # Test development mode
    config.osm_use_dev_api = True
    assert config.current_client_id == "dev_id"
    assert config.current_client_secret == "dev_secret"
    assert config.current_redirect_uri == "https://dev.example/callback"

    # Test production mode
    config.osm_use_dev_api = False
    assert config.current_client_id == "prod_id"
    assert config.current_client_secret == "prod_secret"
    assert config.current_redirect_uri == "https://prod.example/callback"


def test_oauth_config_legacy_fallback(config_factory):
    """Legacy OAuth values remain a fallback when environment values are absent."""
    config = config_factory()
    config.osm_dev_client_id = ""
    config.osm_prod_client_id = ""
    config.osm_dev_client_secret = ""
    config.osm_prod_client_secret = ""
    config.osm_oauth_client_id = "legacy_id"
    config.osm_oauth_client_secret = "legacy_secret"
    config.osm_oauth_redirect_uri = "https://legacy.example/callback"

    for use_dev_api in (True, False):
        config.osm_use_dev_api = use_dev_api
        assert config.current_client_id == "legacy_id"
        assert config.current_client_secret == "legacy_secret"
        assert config.current_redirect_uri == "https://legacy.example/callback"


def test_is_development_mode(config_factory):
    """Test development mode detection."""
    config = config_factory()

    # Test with dev API
    config.osm_use_dev_api = True
    config.development_mode = False
    config.debug = False
    assert config.is_development is True

    # Test with development_mode flag
    config.osm_use_dev_api = False
    config.development_mode = True
    config.debug = False
    assert config.is_development is True

    # Test with debug flag
    config.osm_use_dev_api = False
    config.development_mode = False
    config.debug = True
    assert config.is_development is True

    # Test production mode
    config.osm_use_dev_api = False
    config.development_mode = False
    config.debug = False
    assert config.is_development is False


def test_suite_never_targets_production():
    """The live module singleton must point at the dev API while tests run.

    conftest.py forces OSM_USE_DEV_API=true before import precisely so that an
    accidental live call from a test cannot reach the real OSM database.
    """
    from src.osm_edit_mcp.server import config

    assert config.osm_use_dev_api is True
    assert config.current_api_base_url == config.osm_dev_api_base
    assert "api.openstreetmap.org" not in config.current_api_base_url


def test_working_directory_dotenv_is_never_loaded_implicitly(
    config_factory, monkeypatch, tmp_path: Path
):
    """An MCP host's unrelated or binary .env must not affect startup."""
    (tmp_path / ".env").write_bytes(b"\x00GITCRYPT\xff")
    monkeypatch.chdir(tmp_path)

    config = config_factory()

    assert config.osm_use_dev_api is True
    assert config.default_changeset_created_by.startswith("osm-edit-mcp/")


def test_explicit_dotenv_path_can_be_loaded(config_factory, tmp_path: Path):
    env_file = tmp_path / "operator.env"
    env_file.write_text("DEFAULT_CHANGESET_SOURCE=local-survey\n", encoding="utf-8")
    env_file.chmod(0o600)

    config = config_factory(_env_file=env_file)

    assert config.default_changeset_source == "local-survey"


def test_runtime_dotenv_path_must_be_private_and_not_a_symlink(tmp_path: Path):
    from src.osm_edit_mcp.config import validated_env_file

    env_file = tmp_path / "operator.env"
    env_file.write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
    env_file.chmod(0o600)

    assert validated_env_file(str(env_file)) == env_file

    if os.name == "posix":
        env_file.chmod(0o644)
        with pytest.raises(PermissionError, match="0600"):
            validated_env_file(str(env_file))
        env_file.chmod(0o600)

    link = tmp_path / "linked.env"
    link.symlink_to(env_file)
    with pytest.raises(ValueError, match="symbolic link"):
        validated_env_file(str(link))


def test_library_import_preserves_embedding_host_logging_handlers():
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("OSM_")
    }
    env.update(
        {
            "OSM_USE_DEV_API": "true",
            "USE_KEYRING": "false",
            "ALLOW_PLAINTEXT_TOKEN_FILE": "false",
        }
    )
    code = """
import json
import logging
sentinel = logging.StreamHandler()
root = logging.getLogger()
root.handlers[:] = [sentinel]
from src.osm_edit_mcp import server
print(json.dumps({"preserved": sentinel in root.handlers}))
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"preserved": True}
