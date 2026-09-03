"""Shared test fixtures and suite-wide safety rails.

Two invariants hold for the entire suite:

1. Tests never touch the production OSM API.
2. Tests never opt in to the developer's real dotenv file. Assertions about
   default values must not depend on local credentials, and a failing assertion
   must never print a real client ID or secret into CI logs.

``OSM_USE_DEV_API`` is set at import time because ``osm_edit_mcp.server``
instantiates its configuration singleton at module import, before any fixture
would get a chance to run.
"""

import os
import tempfile
from pathlib import Path

import pytest

for inherited_key in list(os.environ):
    if inherited_key.startswith("OSM_"):
        del os.environ[inherited_key]

_TEST_STATE_DIR = Path(tempfile.gettempdir()) / f"osm-edit-mcp-tests-{os.getpid()}"
_TEST_STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
_TEST_PROPOSAL_DB = _TEST_STATE_DIR / "proposals.sqlite3"

os.environ["OSM_USE_DEV_API"] = "true"
os.environ["OSM_PROPOSAL_DB_PATH"] = str(_TEST_PROPOSAL_DB)
os.environ["OSM_WRITE_PROFILE"] = "safe"
os.environ["ALLOW_PLAINTEXT_TOKEN_FILE"] = "false"
os.environ["USE_KEYRING"] = "false"


@pytest.fixture(autouse=True)
def isolated_osm_env(monkeypatch):
    """Hide local OSM_* environment variables so tests see documented defaults."""
    for key in list(os.environ):
        if key.startswith("OSM_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OSM_USE_DEV_API", "true")
    monkeypatch.setenv(
        "OSM_PROPOSAL_DB_PATH",
        str(_TEST_PROPOSAL_DB),
    )
    monkeypatch.setenv("OSM_WRITE_PROFILE", "safe")
    monkeypatch.setenv("ALLOW_PLAINTEXT_TOKEN_FILE", "false")
    monkeypatch.setenv("USE_KEYRING", "false")


@pytest.fixture
def config_factory():
    """Build an isolated OSMConfig for default-value assertions."""
    from src.osm_edit_mcp.server import OSMConfig

    def _make(**overrides):
        env_file = overrides.pop("_env_file", None)
        return OSMConfig(_env_file=env_file, **overrides)

    return _make
