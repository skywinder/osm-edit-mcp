import pytest
from fastapi import HTTPException

from src.osm_edit_mcp import edit_tools
from src.osm_edit_mcp.server import mcp


class Response:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class Client:
    def __init__(self, text):
        self.text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        return Response(self.text)


@pytest.mark.asyncio
async def test_inspect_map_context_returns_stable_ids_versions_and_geojson(
    monkeypatch,
):
    xml = """<osm>
      <node id="1" version="2" lat="41" lon="44"/>
      <node id="2" version="3" lat="41.001" lon="44.001"/>
      <way id="10" version="7"><nd ref="1"/><nd ref="2"/>
        <tag k="highway" v="residential"/>
      </way>
    </osm>"""
    monkeypatch.setattr(edit_tools, "get_public_client", lambda: Client(xml))

    result = await edit_tools.inspect_map_context(
        "43.99,40.99,44.01,41.01", highway_only=True
    )

    assert result["success"] is True
    assert result["data"]["elements"][0]["id"] == 10
    assert result["data"]["elements"][0]["version"] == 7
    assert (
        result["data"]["geojson"]["features"][0]["properties"]["highway"]
        == "residential"
    )


@pytest.mark.asyncio
async def test_inspect_map_context_rejects_oversized_bbox():
    result = await edit_tools.inspect_map_context("0,0,1,1")

    assert result["success"] is False
    assert "too large" in result["detail"]


def test_safe_profile_does_not_register_raw_write_tools():
    names = {tool.name for tool in mcp._tool_manager.list_tools()}

    assert "apply_osm_edit" in names
    assert "create_track_selection" in names
    assert "create_osm_node" not in names
    assert "create_osm_way" not in names
    assert "find_and_update_place" not in names
    assert "bulk_create_places" not in names


@pytest.mark.asyncio
async def test_http_write_endpoints_are_retired(monkeypatch):
    import web_server

    monkeypatch.setattr(web_server, "API_KEY", "test-key")
    with pytest.raises(HTTPException) as exc:
        await web_server.api_create_changeset(comment="unsafe", api_key="test-key")

    assert exc.value.status_code == 410
