import json
import time

import pytest

from src.osm_edit_mcp import auth, http_client, token_store


class Response:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class Client:
    def __init__(self, details, permissions):
        self.details = details
        self.permissions = permissions

    async def get(self, url):
        return self.permissions if url.endswith("/permissions") else self.details


def test_identity_and_permissions_require_authoritative_fields():
    identity = auth._parse_identity('<osm><user id="42" display_name="mapper"/></osm>')
    permissions = auth._parse_permissions(
        '<osm><permissions><permission name="allow_write_api"/></permissions></osm>'
    )

    assert identity == {"user_id": 42, "username": "mapper"}
    assert auth.has_write_api_permission(permissions)
    with pytest.raises(ValueError, match="identity"):
        auth._parse_identity("<osm/>")


@pytest.mark.asyncio
async def test_verify_write_identity_checks_expiry_and_scope(monkeypatch):
    monkeypatch.setattr(
        auth,
        "load_oauth_token",
        lambda: {"access_token": "secret", "expires_at": time.time() + 60},
    )
    details = Response(200, '<osm><user id="42" display_name="mapper"/></osm>')
    permissions = Response(
        200,
        '<osm><permissions><permission name="allow_write_api"/></permissions></osm>',
    )

    result = await auth.verify_write_identity(Client(details, permissions))
    assert result["user_id"] == 42
    assert result["permissions"] == ["allow_write_api"]

    without_write = Response(200, "<osm><permissions/></osm>")
    with pytest.raises(PermissionError, match="write_api"):
        await auth.verify_write_identity(Client(details, without_write))

    monkeypatch.setattr(
        auth,
        "load_oauth_token",
        lambda: {"access_token": "secret", "expires_at": time.time() - 1},
    )
    with pytest.raises(PermissionError, match="expired"):
        await auth.verify_write_identity(Client(details, permissions))


def test_token_store_uses_keyring_json_and_ignores_plaintext_by_default(
    monkeypatch, tmp_path
):
    values = {}

    def set_password(service, name, value):
        values[(service, name)] = value

    def get_password(service, name):
        return values.get((service, name))

    monkeypatch.setattr(token_store.keyring, "set_password", set_password)
    monkeypatch.setattr(token_store.keyring, "get_password", get_password)
    monkeypatch.setattr(token_store.config, "use_keyring", True)
    monkeypatch.setattr(token_store.config, "allow_plaintext_token_file", False)

    token_store.save_oauth_token(
        {"access_token": "secret", "scope": "write_api"}, use_dev_api=True
    )

    loaded = token_store.load_oauth_token()
    assert loaded == {"access_token": "secret", "scope": "write_api"}
    assert (
        "secret"
        in json.loads(values[("osm-edit-mcp-dev", "token_json")])["access_token"]
    )


def test_secure_plaintext_fallback_only_when_explicitly_enabled(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text('{"access_token":"fallback"}', encoding="utf-8")
    token_path.chmod(0o600)

    def unavailable(*args):
        raise RuntimeError("no keyring")

    monkeypatch.setattr(token_store.keyring, "get_password", unavailable)
    monkeypatch.setattr(token_store.config, "use_keyring", True)
    monkeypatch.setattr(token_store.config, "allow_plaintext_token_file", True)
    monkeypatch.setattr(token_store, "_legacy_token_path", lambda: str(token_path))

    assert token_store.load_oauth_token()["access_token"] == "fallback"

    token_path.chmod(0o644)
    assert token_store.load_oauth_token() is None


@pytest.mark.asyncio
async def test_custom_target_never_receives_official_oauth_token(
    monkeypatch, config_factory
):
    custom_config = config_factory(
        osm_use_dev_api=True,
        osm_api_base_url="https://custom.example/api/0.6",
        osm_allow_custom_api_base=True,
        use_keyring=True,
        allow_plaintext_token_file=True,
    )
    keyring_calls = []

    def record_keyring_call(*args):
        keyring_calls.append(args)
        return "must-not-be-read"

    monkeypatch.setattr(token_store, "config", custom_config)
    monkeypatch.setattr(token_store.keyring, "get_password", record_keyring_call)

    assert token_store.load_oauth_token() is None
    assert keyring_calls == []

    monkeypatch.setattr(http_client, "config", custom_config)
    monkeypatch.setattr(
        http_client,
        "load_oauth_token",
        lambda: pytest.fail("custom target must not load an official OSM token"),
    )
    client = http_client.get_authenticated_client()
    try:
        assert "Authorization" not in client.headers
    finally:
        await client.aclose()

    monkeypatch.setattr(auth, "config", custom_config)
    monkeypatch.setattr(
        auth,
        "load_oauth_token",
        lambda: pytest.fail("custom target must fail before token loading"),
    )
    with pytest.raises(PermissionError, match="custom API targets"):
        await auth.verify_write_identity(Client(Response(200, ""), Response(200, "")))
