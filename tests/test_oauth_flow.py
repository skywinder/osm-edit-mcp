from urllib.parse import parse_qs, urlparse

import pytest

import oauth_auth
from oauth_auth import OSMOAuth


class Response:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class AsyncClient:
    def __init__(self, *, write_permission=True, **kwargs):
        self.write_permission = write_permission

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, data, headers):
        return Response(200, payload={"access_token": "candidate", "expires_in": 60})

    async def get(self, url, headers):
        if url.endswith("/user/details"):
            return Response(200, '<osm><user id="42" display_name="mapper"/></osm>')
        permission = "allow_write_api" if self.write_permission else "allow_read_prefs"
        return Response(
            200,
            f'<osm><permissions><permission name="{permission}"/></permissions></osm>',
        )


def test_oauth_authorization_uses_random_state_pkce_and_least_privilege(monkeypatch):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")
    first = OSMOAuth(use_dev_api=True)
    second = OSMOAuth(use_dev_api=True)

    query = parse_qs(urlparse(first.get_authorization_url()).query)

    assert query["state"] == [first.state]
    assert first.state != second.state
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) >= 43
    assert set(query["scope"][0].split()) == {"read_prefs", "write_api"}


def test_existing_token_metadata_is_loaded_without_exposing_secrets(
    monkeypatch, capsys
):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")

    def unavailable(*args):
        raise RuntimeError("must-not-appear")

    monkeypatch.setattr(oauth_auth.keyring, "get_password", unavailable)

    token, has_existing_record = OSMOAuth(
        use_dev_api=True
    ).load_existing_token_record()

    output = capsys.readouterr().out
    assert token == {}
    assert has_existing_record is True
    assert "RuntimeError" in output
    assert "must-not-appear" not in output


def test_malformed_token_metadata_does_not_abort_reauthorization(monkeypatch):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")

    def get_password(service, name):
        return "not-json" if name == "token_json" else None

    monkeypatch.setattr(oauth_auth.keyring, "get_password", get_password)

    token, has_existing_record = OSMOAuth(
        use_dev_api=True
    ).load_existing_token_record()

    assert token == {}
    assert has_existing_record is True


def test_replacement_gate_uses_persisted_identity_after_live_failure():
    assert oauth_auth._replacement_account_gate(
        has_existing_record=True,
        stored_token={"access_token": "old", "user_id": "42"},
        live_identity=None,
        allow_account_change=False,
    ) == (True, 42)


def test_replacement_gate_requires_explicit_unknown_account_change():
    arguments = {
        "has_existing_record": True,
        "stored_token": {"access_token": "old"},
        "live_identity": None,
    }

    assert oauth_auth._replacement_account_gate(
        **arguments, allow_account_change=False
    ) == (False, None)
    assert oauth_auth._replacement_account_gate(
        **arguments, allow_account_change=True
    ) == (True, None)


@pytest.mark.parametrize("error", [EOFError(), KeyboardInterrupt()])
def test_redirect_prompt_cancellation_exits_cleanly(monkeypatch, capsys, error):
    def cancelled(prompt):
        raise error

    monkeypatch.setattr(oauth_auth.getpass, "getpass", cancelled)

    assert oauth_auth._prompt_for_redirect_url() is None
    assert "existing token is unchanged" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_token_exchange_does_not_persist_unvalidated_token(monkeypatch):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(oauth_auth.httpx, "AsyncClient", AsyncClient)
    monkeypatch.setattr(
        oauth_auth,
        "save_oauth_token",
        lambda *args, **kwargs: pytest.fail("exchange must not persist a token"),
    )

    token = await OSMOAuth(use_dev_api=True).exchange_code_for_token("code")

    assert token["access_token"] == "candidate"


@pytest.mark.asyncio
async def test_candidate_token_is_saved_only_after_identity_and_scope(monkeypatch):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")
    clients = [AsyncClient(write_permission=False), AsyncClient(write_permission=True)]
    monkeypatch.setattr(
        oauth_auth.httpx, "AsyncClient", lambda **kwargs: clients.pop(0)
    )
    saved = []
    monkeypatch.setattr(
        oauth_auth,
        "save_oauth_token",
        lambda token, **kwargs: saved.append((token.copy(), kwargs)),
    )
    oauth = OSMOAuth(use_dev_api=True)

    assert await oauth.validate_and_save_token({"access_token": "rejected"}) is None
    assert saved == []

    identity = await oauth.validate_and_save_token(
        {"access_token": "accepted"}, expected_user_id=42
    )
    assert identity["user_id"] == 42
    assert saved[0][0]["user_id"] == 42


@pytest.mark.asyncio
async def test_candidate_token_cannot_silently_change_accounts(monkeypatch):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(oauth_auth.httpx, "AsyncClient", AsyncClient)
    monkeypatch.setattr(
        oauth_auth,
        "save_oauth_token",
        lambda *args, **kwargs: pytest.fail("mismatched account must not be saved"),
    )

    result = await OSMOAuth(use_dev_api=True).validate_and_save_token(
        {"access_token": "candidate"}, expected_user_id=99
    )

    assert result is None


@pytest.mark.asyncio
async def test_token_save_failure_is_sanitized(monkeypatch, capsys):
    monkeypatch.setenv("OSM_DEV_CLIENT_ID", "client-id")
    monkeypatch.setenv("OSM_DEV_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(oauth_auth.httpx, "AsyncClient", AsyncClient)

    def fail_to_save(*args, **kwargs):
        raise RuntimeError("candidate-secret-must-not-appear")

    monkeypatch.setattr(oauth_auth, "save_oauth_token", fail_to_save)

    result = await OSMOAuth(use_dev_api=True).validate_and_save_token(
        {"access_token": "candidate"}, expected_user_id=42
    )

    output = capsys.readouterr().out
    assert result is None
    assert "RuntimeError" in output
    assert "candidate-secret-must-not-appear" not in output
