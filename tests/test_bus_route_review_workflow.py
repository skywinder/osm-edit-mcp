"""Replay road choices and use the resulting directed GeoJSON over MCP."""

from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from osm_edit_mcp import transit_corridor, transit_match
from osm_edit_mcp.server import mcp


@pytest.mark.asyncio
async def test_mapper_reviews_parallel_roads_and_searches_the_selected_path(
    monkeypatch,
):
    roads = [
        {
            "id": way_id,
            "version": 3,
            "nodes": [way_id * 10, way_id * 10 + 1],
            "geometry": [{"lat": lat, "lon": lon} for lon in (68.76, 68.761)],
            "tags": {"highway": "service", "oneway": "yes"},
        }
        for way_id, lat in [(1, 38.52), (2, 38.52001)]
    ]
    monkeypatch.setattr(
        transit_match, "_load_highways", AsyncMock(return_value=(roads, {}))
    )

    def stop_map(request):
        assert request.method == "GET" and request.url.path.endswith("/map")
        return httpx.Response(
            200,
            text='<osm><node id="7" lat="38.51995" lon="68.7605">'
            '<tag k="highway" v="bus_stop"/><tag k="name" v="Бозор"/></node></osm>',
        )

    monkeypatch.setattr(
        transit_corridor,
        "get_public_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(stop_map)),
    )
    points = [{"lat": 38.52, "lon": lon} for lon in (68.7601, 68.7609)]
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "suggest_bus_route_ways", {"points": points, "include_snap_geojson": True}
        )
        original = result.structuredContent["data"]
        assert original["ambiguous_point_indices"] == [0, 1]
        features = original["snap_review_geojson"]["features"]
        assert features[0]["geometry"] == {
            "type": "Point",
            "coordinates": [points[0]["lon"], points[0]["lat"]],
        }
        choices = [
            next(
                candidate["choice"]
                for candidate in review["candidates"]
                if candidate["way_id"] == 2
            )
            for review in original["snap_reviews"]
        ]
        road_feature = next(f for f in features if f["properties"].get("way_id") == 2)
        assert road_feature["geometry"] == {
            "type": "LineString",
            "coordinates": [[68.76, 38.52001], [68.761, 38.52001]],
        }
        assert road_feature["properties"]["selected"] is False
        assert (
            road_feature["properties"]["start_node_id"] == choices[0]["start_node_id"]
        )

        result = await session.call_tool(
            "suggest_bus_route_ways", {"points": points, "snap_choices": choices}
        )
        selected = result.structuredContent["data"]
        assert selected["ordered_way_ids"] == [2]
        assert selected["gaps"] == selected["ambiguous_point_indices"] == []
        result = await session.call_tool(
            "suggest_bus_route_stops",
            {"matched_geojson": selected["matched_geojson"], "provider": "editing_api"},
        )
    assert result.structuredContent["success"]
    assert [row["name"] for row in result.structuredContent["data"]["candidates"]] == [
        "Бозор"
    ]
