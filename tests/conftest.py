"""Shared test fixtures and suite-wide safety rails.

Two invariants hold for the entire suite:

1. Tests never touch the production OSM API, whatever ``.env`` says. The server
   is normally configured for production, so this must be forced here rather
   than left to local configuration.
2. Tests never read the developer's real ``.env``. Assertions about default
   values must not depend on local credentials, and a failing assertion must
   never print a real client ID or secret into CI logs.

``OSM_USE_DEV_API`` is set at import time because ``osm_edit_mcp.server``
instantiates its configuration singleton at module import, before any fixture
would get a chance to run. Environment variables take precedence over the
dotenv file in pydantic-settings, so this wins over ``.env``.
"""

import os

import pytest

os.environ["OSM_USE_DEV_API"] = "true"
os.environ["OSM_PROPOSAL_DB_PATH"] = (
    f"/private/tmp/osm-edit-mcp-tests-{os.getpid()}.sqlite3"
)
os.environ["OSM_WRITE_PROFILE"] = "safe"


@pytest.fixture(autouse=True)
def isolated_osm_env(monkeypatch):
    """Hide local OSM_* environment variables so tests see documented defaults."""
    for key in list(os.environ):
        if key.startswith("OSM_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OSM_USE_DEV_API", "true")
    monkeypatch.setenv(
        "OSM_PROPOSAL_DB_PATH",
        f"/private/tmp/osm-edit-mcp-tests-{os.getpid()}.sqlite3",
    )
    monkeypatch.setenv("OSM_WRITE_PROFILE", "safe")


@pytest.fixture
def config_factory():
    """Build an OSMConfig that ignores the on-disk .env file.

    Use this instead of ``OSMConfig()`` anywhere a test asserts on defaults.
    """
    from src.osm_edit_mcp.server import OSMConfig

    def _make(**overrides):
        return OSMConfig(_env_file=None, **overrides)

    return _make
