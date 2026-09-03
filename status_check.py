#!/usr/bin/env python3
"""Report source-checkout readiness without exposing OAuth material."""

from __future__ import annotations

import os
from pathlib import Path

from osm_edit_mcp.config import config
from osm_edit_mcp.token_store import get_current_user_info

ROOT = Path(__file__).resolve().parent


def check_setup_status() -> int:
    """Check the package, explicit configuration, and optional authentication."""
    print("OSM Edit MCP Server - Setup Status Check")
    print("=" * 48)

    has_error = False
    configured_env = os.environ.get("OSM_EDIT_MCP_ENV_FILE")
    if configured_env:
        env_path = Path(configured_env).expanduser()
        if env_path.is_file():
            print("OK  Explicit dotenv configuration exists")
        else:
            print("ERR OSM_EDIT_MCP_ENV_FILE does not point to a file")
            has_error = True
    else:
        print("OK  No dotenv selected; documented safe defaults are active")

    environment = config.api_environment.title()
    print(f"OK  API mode: {environment}")
    print(f"OK  API target: {config.current_api_base_url}")
    print(f"OK  Write profile: {config.osm_write_profile}")

    client_id = config.current_client_id
    client_secret = config.current_client_secret
    oauth_configured = bool(client_id and client_secret)
    print(
        "OK  OAuth application credentials: configured"
        if oauth_configured
        else "INFO OAuth credentials are absent; read-only inspection remains available"
    )

    user_info = get_current_user_info()
    if user_info:
        user_label = user_info.get("username") or user_info.get("user_id") or "unknown"
        print(f"OK  Authentication token is available for: {user_label}")
    else:
        print("INFO No OAuth token found in the configured secure token store")

    required_files = (
        "pyproject.toml",
        "uv.lock",
        "src/osm_edit_mcp/server.py",
        "oauth_auth.py",
    )
    for relative_path in required_files:
        if (ROOT / relative_path).is_file():
            print(f"OK  {relative_path}")
        else:
            print(f"ERR Missing required source file: {relative_path}")
            has_error = True

    print("\nNext steps:")
    if has_error:
        print("1. Fix the errors above, then run this check again.")
    elif not oauth_configured:
        print("1. Read-only setup is ready: start through an MCP host with uvx.")
        print(
            "2. Configure OAuth only if you intend to prepare authenticated previews."
        )
    elif not user_info:
        print("1. Run: uv run --locked python oauth_auth.py")
        print("2. Start through an MCP host with: uv run --locked osm-edit-mcp")
    else:
        print("1. Setup is ready. Start through an MCP host with uvx osm-edit-mcp.")

    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(check_setup_status())
