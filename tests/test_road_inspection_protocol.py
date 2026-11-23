"""Exercise the restricted profile over stdio with synthetic GPX and OSM data."""

import sys
from pathlib import Path
from textwrap import dedent

import anyio
import pytest
from mcp import ClientSession, McpError, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,environment",
    [
        ("https://overpass-api.de/api/interpreter", "production"),
        ("https://fixture.example/osm", "custom"),
    ],
)
async def test_road_inspection_reads_production_geometry_without_write_tools(
    tmp_path, endpoint, environment
):
    # Intercept the HTTP transport in the child. The SDK and our normal public
    # client still construct the actual URL, headers and query parameters.
    server = dedent("""
        import httpx
        import os
        from urllib.parse import parse_qs
        from osm_edit_mcp.server import main

        async def fixture_read(self, request):
            assert request.method == "POST"
            assert str(request.url) == os.environ["OSM_OVERPASS_URL"]
            query = parse_qs(request.content.decode())["data"][0]
            assert 'way["highway"](' in query and "out meta geom 1001" in query
            assert "trkpt" not in query
            assert "Authorization" not in request.headers
            assert "osm-edit-mcp" in request.headers["User-Agent"]
            return httpx.Response(200, json={
                "osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"},
                "elements": [{
                    "type": "way", "id": 17, "version": 4, "nodes": [11,12],
                    "geometry": [{"lat": 41, "lon": 44}, {"lat": 41.0002, "lon": 44.0002}],
                    "tags": {"highway": "service"}
                }]
            })

        httpx.AsyncHTTPTransport.handle_async_request = fixture_read
        main()
    """)
    db = tmp_path / "proposals.sqlite3"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", server],
        env={
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "OSM_TOOL_PROFILE": "road-inspection",
            "OSM_OVERPASS_URL": endpoint,
            "OSM_USE_DEV_API": "true",
            "OSM_WRITE_PROFILE": "expert",
            "OSM_PROPOSAL_DB_PATH": str(db),
            "USE_KEYRING": "false",
            "LOG_LEVEL": "ERROR",
        },
    )
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="41" lon="44"/><trkpt lat="41.0001" lon="44.0001"/>
      <trkpt lat="41.0002" lon="44.0002"/>
    </trkseg></trk></gpx>"""
    with anyio.fail_after(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert {item.name for item in tools} == {
                    "analyze_gpx_track",
                    "create_track_selection",
                    "compare_track_selections",
                    "match_track_selection",
                    "suggest_track_road_candidates",
                }
                assert all(item.annotations.readOnlyHint for item in tools)
                templates = (await session.list_resource_templates()).resourceTemplates
                assert {item.uriTemplate for item in templates} == {
                    "ui://osm-edit/track-selection/{selection_id}",
                    "ui://osm-edit/track-comparison/{comparison_id}",
                }
                assert not (await session.list_prompts()).prompts
                assert not (await session.list_resources()).resources

                async def data(name, args):
                    result = await session.call_tool(name, args)
                    assert not result.isError
                    payload = result.structuredContent
                    payload = payload.get("result", payload)
                    assert payload["success"]
                    return payload["data"]

                track = await data("analyze_gpx_track", {"gpx_xml": gpx})
                selection = await data(
                    "create_track_selection",
                    {
                        "track_id": track["track_id"],
                        "segment_id": track["segments"][0]["segment_id"],
                        "start_point_index": 0,
                        "end_point_index": 2,
                    },
                )
                assert (await session.read_resource(selection["preview_uri"])).contents
                other_track = await data(
                    "analyze_gpx_track", {"gpx_xml": gpx.replace("41.0001", "41.00012")}
                )
                other_selection = await data(
                    "create_track_selection",
                    {
                        "track_id": other_track["track_id"],
                        "segment_id": other_track["segments"][0]["segment_id"],
                        "start_point_index": 0,
                        "end_point_index": 2,
                    },
                )
                comparison = await data(
                    "compare_track_selections",
                    {
                        "selection_ids": [
                            selection["selection_id"],
                            other_selection["selection_id"],
                        ]
                    },
                )
                overlay = await session.read_resource(comparison["preview_uri"])
                assert overlay.contents[0].mimeType == "text/html"
                assert "Trace 1" in overlay.contents[0].text
                result = await data(
                    "suggest_track_road_candidates",
                    {"selection_id": selection["selection_id"]},
                )
                assert result["environment"] == environment
                assert result["provider"] == "Overpass"
                assert result["api_target"] == endpoint
                assert result["data_timestamp"] == "2026-01-01T00:00:00Z"
                assert "© OpenStreetMap contributors" in result["attribution"]
                assert (
                    "https://www.openstreetmap.org/copyright" in result["attribution"]
                )
                (way,) = result["candidates"]
                assert (way["way_id"], way["version"]) == (17, 4)
                assert way["geometry"] == {
                    "type": "LineString",
                    "coordinates": [[44.0, 41.0], [44.0002, 41.0002]],
                }
                for name in (
                    "apply_osm_edit",
                    "preview_track_road_edit",
                    "create_changeset",
                ):
                    assert (await session.call_tool(name, {})).isError
                with pytest.raises(McpError):
                    await session.read_resource("ui://osm-edit/proposal/example")
    assert not db.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("many_points,large_tags", [(True, False), (False, True)])
async def test_oversize_geometry_can_be_retried_with_a_lower_limit(
    monkeypatch, many_points, large_tags
):
    from osm_edit_mcp import track_tools

    gpx = '<gpx><trk><trkseg><trkpt lat="41" lon="44"/><trkpt lat="41.0002" lon="44.0002"/></trkseg></trk></gpx>'
    line = [{"lat": 41, "lon": 44}, {"lat": 41.0002, "lon": 44.0002}]
    ways = [
        {
            "type": "way",
            "id": index + 1,
            "version": 1,
            "geometry": line * (1000 if many_points else 1),
            "tags": {"highway": "service", "name": "a" * (50000 if large_tags else 1)},
        }
        for index in range(3)
    ]

    async def fake_overpass(query):
        return {"elements": ways}

    monkeypatch.setattr(track_tools.config, "osm_tool_profile", "road-inspection")
    monkeypatch.setattr(track_tools.overpass, "execute", fake_overpass)
    args = {"gpx_xml": gpx, "segment_id": "trk-0-seg-0"}
    large = await track_tools.suggest_track_road_candidates(**args, limit=50)
    assert not large["success"]
    assert "Reduce limit" in large["error"]
    small = await track_tools.suggest_track_road_candidates(**args, limit=1)
    assert small["success"]
    assert len(small["data"]["candidates"]) == 1
