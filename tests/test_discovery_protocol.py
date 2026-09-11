"""Run a real stdio client against local HTTP fixtures, never public services."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_discovery_stdio_resolve_search_details_and_errors(tmp_path):
    requests = []
    node = {
        "type": "node",
        "id": 42,
        "lat": 40.18,
        "lon": 44.51,
        "tags": {
            "amenity": "cafe",
            "name": "Fixture",
            "name:ru": "Тестовое кафе",
            "opening_hours": "24/7",
            "internet_access": "wlan",
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if status == 429:
                self.send_header("Retry-After", "300")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_GET(self):
            requests.append(("GET", self.path, self.headers.get("Authorization")))
            assert urlparse(self.path).path == "/search"
            self.respond(
                [
                    {
                        "osm_type": "node",
                        "osm_id": 42,
                        "display_name": "Fixture area",
                        "lat": "40.18",
                        "lon": "44.51",
                        "category": "place",
                        "type": "suburb",
                        "boundingbox": ["40.17", "40.19", "44.5", "44.52"],
                    }
                ]
            )

        def do_POST(self):
            query = parse_qs(
                self.rfile.read(int(self.headers["Content-Length"])).decode()
            )["data"][0]
            requests.append(("POST", query, self.headers.get("Authorization")))
            if '"museum"' in query:
                self.respond({}, status=429)
            else:
                self.respond(
                    {
                        "elements": [node],
                        "osm3s": {"timestamp_osm_base": "2026-09-08T00:00:00Z"},
                    }
                )

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{http.server_port}"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from osm_edit_mcp.server import main; main()"],
            env={
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "OSM_TOOL_PROFILE": "discovery",
                "OSM_USE_DEV_API": "true",
                "OSM_WRITE_PROFILE": "expert",
                "OSM_REQUIRE_HOST_CONFIRMATION": "false",
                "USE_KEYRING": "false",
                "LOG_LEVEL": "ERROR",
                "OSM_PROPOSAL_DB_PATH": str(tmp_path / "must-not-exist.sqlite3"),
                "OSM_OVERPASS_URL": base,
                "OSM_NOMINATIM_URL": base,
            },
        )
        try:
            with anyio.fail_after(30):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        assert {t.name for t in tools} == {
                            "resolve_location",
                            "search_nearby_places",
                            "get_place_details",
                        }
                        assert all(t.annotations.readOnlyHint for t in tools)
                        search = next(
                            t for t in tools if t.name == "search_nearby_places"
                        )
                        assert (
                            search.inputSchema["properties"]["radius_meters"]["maximum"]
                            == 10000
                        )
                        assert "enum" in json.dumps(
                            search.inputSchema["properties"]["categories"]
                        )
                        assert "preference_matches" in json.dumps(search.outputSchema)
                        assert not (
                            await session.list_resource_templates()
                        ).resourceTemplates
                        assert not (await session.list_prompts()).prompts
                        location = await session.call_tool(
                            "resolve_location",
                            {"query": "Тест", "language": "ru", "countrycodes": ["AM"]},
                        )
                        assert not location.isError
                        assert location.structuredContent["data"]["candidates"][0][
                            "bbox"
                        ] == [44.5, 40.17, 44.52, 40.19]
                        result = await session.call_tool(
                            "search_nearby_places",
                            {
                                "lat": 40.18,
                                "lon": 44.51,
                                "categories": ["cafe"],
                                "language": "ru",
                                "preferred_tags": {"internet_access": "wlan"},
                                "open_now": True,
                            },
                        )
                        assert not result.isError
                        place = result.structuredContent["data"]["places"][0]
                        assert (
                            place["name"] == "Тестовое кафе"
                            and place["distance_meters"] == 0
                        )
                        details = await session.call_tool(
                            "get_place_details", {"place_ref": place["place_ref"]}
                        )
                        assert not details.isError
                        assert details.structuredContent["data"]["place"]["id"] == 42
                        before = len(requests)
                        invalid = await session.call_tool(
                            "search_nearby_places",
                            {"lat": 0, "lon": 0, "categories": ["not-a-category"]},
                        )
                        assert invalid.isError and len(requests) == before
                        busy = await session.call_tool(
                            "search_nearby_places",
                            {"lat": 0, "lon": 0, "categories": ["museum"]},
                        )
                        assert busy.isError
                        assert (
                            busy.structuredContent["error_details"][
                                "retry_after_seconds"
                            ]
                            == 300
                        )
                        before = len(requests)
                        again = await session.call_tool(
                            "get_place_details", {"place_ref": "osm:node:43"}
                        )
                        assert again.isError and len(requests) == before
            assert all(auth is None for _, _, auth in requests)
            assert not (tmp_path / "must-not-exist.sqlite3").exists()
        finally:
            http.shutdown()
            worker.join(timeout=5)
