"""OAuth token loading and identity metadata.

The current storage format remains compatible with the legacy server. Keeping
it behind this module makes a later keyring-only migration local and testable.
"""

import json
import os
import stat
from typing import Any, Dict, Optional

import keyring

from .config import config, logger


def _keyring_service(use_dev_api: Optional[bool] = None) -> str:
    if use_dev_api is None:
        if config.api_environment == "custom":
            raise ValueError("OAuth token storage is disabled for custom API targets")
        selected = config.is_development_api
    else:
        selected = use_dev_api
    return f"osm-edit-mcp-{'dev' if selected else 'prod'}"


def _legacy_token_path() -> str:
    if config.api_environment == "custom":
        raise ValueError("OAuth token files are disabled for custom API targets")
    return (
        ".osm_token_dev.json" if config.is_development_api else ".osm_token_prod.json"
    )


def save_oauth_token(
    token_data: Dict[str, Any], *, use_dev_api: Optional[bool] = None
) -> None:
    """Store the complete OAuth token in the OS keyring.

    Plaintext files are intentionally not written. Existing token files are left
    untouched so migration is non-destructive, but are ignored by default.
    """
    if not token_data.get("access_token"):
        raise ValueError("OAuth token is missing access_token")
    keyring.set_password(
        _keyring_service(use_dev_api), "token_json", json.dumps(token_data)
    )


def load_oauth_token() -> Optional[Dict[str, Any]]:
    """Load OAuth data from keyring, with an explicit secure-file fallback."""
    if config.api_environment == "custom":
        logger.debug("OAuth token loading is disabled for custom API targets")
        return None
    if config.use_keyring:
        try:
            serialized = keyring.get_password(_keyring_service(), "token_json")
            if serialized:
                token_data = json.loads(serialized)
                if isinstance(token_data, dict) and token_data.get("access_token"):
                    return token_data

            # Backward compatibility with the original keyring layout. This does
            # not consult the plaintext backup.
            access_token = keyring.get_password(_keyring_service(), "access_token")
            if access_token:
                token_data = {"access_token": access_token}
                refresh_token = keyring.get_password(
                    _keyring_service(), "refresh_token"
                )
                if refresh_token:
                    token_data["refresh_token"] = refresh_token
                return token_data
        except Exception as exc:
            logger.warning("OS keyring is unavailable: %s", type(exc).__name__)

    try:
        if config.allow_plaintext_token_file:
            token_file = _legacy_token_path()
            if os.path.exists(token_file):
                mode = stat.S_IMODE(os.stat(token_file, follow_symlinks=False).st_mode)
                if mode & 0o077:
                    logger.error(
                        "Refusing OAuth token file %s with permissions %o; require 0600",
                        token_file,
                        mode,
                    )
                    return None
                with open(token_file, "r", encoding="utf-8") as handle:
                    token_data = json.load(handle)
                if isinstance(token_data, dict) and token_data.get("access_token"):
                    return token_data
        return None
    except Exception as exc:
        logger.error("Failed to load OAuth token: %s", type(exc).__name__)
        return None


def get_current_user_info() -> Optional[Dict[str, Any]]:
    """Get current authenticated user information"""
    token_data = load_oauth_token()
    if token_data:
        return {
            "user_id": token_data.get("user_id"),
            "username": token_data.get("username"),
            "expires_at": token_data.get("expires_at"),
            "scopes": token_data.get("scope", "").split(),
        }
    return None


__all__ = ["get_current_user_info", "load_oauth_token", "save_oauth_token"]
