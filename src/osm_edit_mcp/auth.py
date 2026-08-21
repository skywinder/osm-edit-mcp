"""Authoritative OSM OAuth identity and permission checks."""

import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config
from .token_store import load_oauth_token

WRITE_API_PERMISSION_NAMES = {"write_api", "allow_write_api"}


def _token_is_expired(token: Dict[str, Any]) -> bool:
    expires_at = token.get("expires_at")
    if expires_at is None:
        return False
    if isinstance(expires_at, (int, float)):
        return float(expires_at) <= time.time()
    if isinstance(expires_at, str):
        value = expires_at.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc)
    return True


def _parse_identity(xml_text: str) -> Dict[str, Any]:
    root = parse_xml(xml_text)
    user = root.find(".//user")
    if user is None or not user.get("id") or not user.get("display_name"):
        raise ValueError("OSM user/details response did not contain an identity")
    return {
        "user_id": int(user.get("id", "0")),
        "username": user.get("display_name", ""),
    }


def _parse_permissions(xml_text: str) -> set[str]:
    root = parse_xml(xml_text)
    permissions = set()
    for element in root.findall(".//permission"):
        name = element.get("name")
        if name:
            permissions.add(name)
    return permissions


def has_write_api_permission(permissions: Iterable[str]) -> bool:
    return bool(WRITE_API_PERMISSION_NAMES.intersection(permissions))


async def verify_write_identity(client: Any) -> Dict[str, Any]:
    """Verify the live OSM account and write scope before every apply."""
    token = load_oauth_token()
    if not token or not token.get("access_token"):
        raise PermissionError("Authentication required")
    if _token_is_expired(token):
        raise PermissionError("OAuth token is expired; authenticate again")
    config.assert_safe_api_target(config.current_api_base_url)

    details = await client.get(f"{config.current_api_base_url}/user/details")
    if details.status_code != 200:
        raise PermissionError(
            f"OSM identity verification failed with HTTP {details.status_code}"
        )
    identity = _parse_identity(details.text)

    permissions_response = await client.get(
        f"{config.current_api_base_url}/permissions"
    )
    if permissions_response.status_code != 200:
        raise PermissionError(
            "OSM permission verification failed with HTTP "
            f"{permissions_response.status_code}"
        )
    permissions = _parse_permissions(permissions_response.text)
    if not has_write_api_permission(permissions):
        raise PermissionError("OAuth token does not grant write_api")

    return {**identity, "permissions": sorted(permissions)}


__all__ = [
    "has_write_api_permission",
    "verify_write_identity",
    "_parse_identity",
    "_parse_permissions",
    "_token_is_expired",
]
