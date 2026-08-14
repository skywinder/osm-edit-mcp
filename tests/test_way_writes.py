import xml.etree.ElementTree as ET

import pytest

from src.osm_edit_mcp import write_tools


class Response:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class Client:
    def __init__(self):
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        self.requests.append(("GET", url, None))
        return Response(
            text='<osm><way id="9" version="4"><nd ref="1"/><nd ref="2"/>'
            '<tag k="highway" v="service"/></way></osm>'
        )

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return Response(text="99")

    async def put(self, url, **kwargs):
        self.requests.append(("PUT", url, kwargs))
        return Response(text="5")


@pytest.mark.asyncio
async def test_create_osm_way_performs_authenticated_write(monkeypatch):
    client = Client()
    monkeypatch.setattr(write_tools, "load_oauth_token", lambda: {"access_token": "x"})
    monkeypatch.setattr(write_tools, "get_authenticated_client", lambda: client)

    result = await write_tools.create_osm_way(
        [1, 2], {"highway": "service", "name": "A&B"}, changeset_id=7
    )

    assert result["success"] is True
    assert result["data"]["way_id"] == 99
    method, url, request = client.requests[0]
    assert method == "POST"
    assert url.endswith("/ways")
    root = ET.fromstring(request["content"])
    assert root.find(".//tag[@k='name']").get("v") == "A&B"


@pytest.mark.asyncio
async def test_update_osm_way_fetches_and_uses_current_version(monkeypatch):
    client = Client()
    monkeypatch.setattr(write_tools, "load_oauth_token", lambda: {"access_token": "x"})
    monkeypatch.setattr(write_tools, "get_authenticated_client", lambda: client)

    result = await write_tools.update_osm_way(
        9, [1, 3, 2], {"highway": "service"}, changeset_id=7
    )

    assert result["success"] is True
    assert result["data"]["version"] == 5
    method, url, request = client.requests[-1]
    assert method == "PUT"
    assert url.endswith("/way/9")
    way = ET.fromstring(request["content"]).find(".//way")
    assert way.get("version") == "4"
    assert [nd.get("ref") for nd in way.findall("nd")] == ["1", "3", "2"]


@pytest.mark.asyncio
async def test_way_writes_refuse_missing_authentication(monkeypatch):
    monkeypatch.setattr(write_tools, "load_oauth_token", lambda: None)

    create = await write_tools.create_osm_way(
        [1, 2], {"highway": "service"}, changeset_id=7
    )
    update = await write_tools.update_osm_way(
        9, [1, 2], {"highway": "service"}, changeset_id=7
    )

    assert create["success"] is False
    assert update["success"] is False
    assert create["error"] == "Authentication required"
