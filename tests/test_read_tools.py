import xml.etree.ElementTree as ET

import pytest

from src.osm_edit_mcp import read_tools


class Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Client:
    def __init__(self, response):
        self.response = response
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        self.urls.append(url)
        return self.response


@pytest.mark.asyncio
async def test_get_osm_way_uses_public_client(monkeypatch):
    client = Client(
        Response(
            '<osm><way id="1550120134" version="1">'
            '<nd ref="1"/><nd ref="2"/>'
            '<tag k="highway" v="residential"/></way></osm>'
        )
    )
    monkeypatch.setattr(read_tools, "get_public_client", lambda: client)

    result = await read_tools.get_osm_way(1550120134)

    assert result["success"] is True
    assert result["data"]["elements"][0]["id"] == 1550120134
    assert result["data"]["elements"][0]["tags"] == {"highway": "residential"}
    assert client.urls == [f"{read_tools.config.current_api_base_url}/way/1550120134"]


@pytest.mark.asyncio
async def test_get_changeset_returns_changeset_data(monkeypatch):
    client = Client(
        Response(
            '<osm><changeset id="187530272" open="false" changes_count="16" '
            'comments_count="0" user="sky-is-here" uid="23063276" '
            'min_lat="41.758" min_lon="41.762" max_lat="41.759" '
            'max_lon="41.764">'
            '<tag k="comment" v="Add surveyed residential road"/>'
            "</changeset></osm>"
        )
    )
    monkeypatch.setattr(read_tools, "get_public_client", lambda: client)

    result = await read_tools.get_changeset(187530272)

    assert result["success"] is True
    changeset = result["data"]["elements"][0]
    assert changeset["id"] == 187530272
    assert changeset["open"] is False
    assert changeset["changes_count"] == 16
    assert changeset["tags"]["comment"] == "Add surveyed residential road"


@pytest.mark.asyncio
async def test_get_changeset_history_uses_shared_config_and_client(monkeypatch):
    client = Client(
        Response(
            '<osm><changeset id="187530272" open="false" changes_count="16" '
            'user="sky-is-here" uid="23063276">'
            '<tag k="comment" v="Add surveyed residential road"/>'
            "</changeset></osm>"
        )
    )
    monkeypatch.setattr(read_tools, "get_public_client", lambda: client)

    result = await read_tools.get_changeset_history(user_id=23063276, limit=5)

    assert result["success"] is True
    assert result["data"]["changesets"][0]["id"] == 187530272
    assert result["data"]["changesets"][0]["tags"]["comment"] == (
        "Add surveyed residential road"
    )
    assert client.urls == [
        f"{read_tools.config.current_api_base_url}/changesets?limit=5&user=23063276"
    ]


@pytest.mark.asyncio
async def test_export_osm_xml_escapes_tags(monkeypatch):
    async def fake_area(_bbox):
        return {
            "success": True,
            "data": {
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "lat": 41.0,
                        "lon": 42.0,
                        "tags": {"name": 'A&B "Road"'},
                    }
                ]
            },
        }

    monkeypatch.setattr(read_tools, "get_osm_elements_in_area", fake_area)

    result = await read_tools.export_osm_data("41,42,43,44", format="xml")

    assert result["success"] is True
    root = ET.fromstring(result["data"]["exported_data"])
    assert root.find(".//tag").get("v") == 'A&B "Road"'


@pytest.mark.asyncio
async def test_natural_language_parser_never_suggests_unregistered_writes():
    result = await read_tools.parse_natural_language_osm_request(
        "Add a cafe named Survey Stop"
    )

    assert result["success"] is True
    suggestions = result["data"]["action_suggestions"]
    assert "not supported" in suggestions["delete"]
    assert "safe profile" in suggestions["create"]
    assert "safe profile" in suggestions["update"]
    assert "create_place_from_description" not in str(suggestions)
    assert "find_and_update_place" not in str(suggestions)
    assert "delete_place_from_description" not in str(suggestions)
