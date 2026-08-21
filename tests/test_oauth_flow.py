from urllib.parse import parse_qs, urlparse

from oauth_auth import OSMOAuth


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
