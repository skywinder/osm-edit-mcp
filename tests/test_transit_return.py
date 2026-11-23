"""Independent return survey, boarding side, missing counterparts and detours."""

from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from osm_edit_mcp import transit_corridor as corridor
from osm_edit_mcp import transit_match as matcher
from osm_edit_mcp import transit_return as returning
from osm_edit_mcp.server import mcp

A, B, C = [(38.52, lon) for lon in (68.760, 68.761, 68.762)]


def way(identifier, refs, positions):
    return {
        "id": identifier,
        "version": 1,
        "nodes": refs,
        "tags": {"highway": "residential"},
        "geometry": [{"lat": p[0], "lon": p[1]} for p in positions],
    }


def stop(identifier, lat, lon, name):
    return {
        "id": identifier,
        "lat": lat,
        "lon": lon,
        "version": 1,
        "tags": {"highway": "bus_stop", "name": name},
    }


@pytest.mark.asyncio
async def test_two_independent_matches_flow_through_mcp_with_local_names(monkeypatch):
    roads = [way(10, [1, 2], [A, B]), way(11, [2, 3], [B, C])]
    monkeypatch.setattr(matcher, "_load_highways", AsyncMock(return_value=(roads, {})))
    outward_nodes = [
        stop(101, 38.51995, 68.7604, "First"),
        stop(102, 38.51995, 68.7616, "Second"),
        stop(103, 38.53, 68.762, "Outward branch"),
    ]
    return_nodes = [
        stop(201, 38.52005, 68.7604, "Local name"),
        stop(202, 38.52005, 68.7616, "Second"),
        stop(203, 38.52005, 68.761, "Return only"),
    ]
    reads = []

    def api(request):
        assert request.method == "GET"
        if request.url.path.endswith("/nodes"):
            assert request.url.params["nodes"] == "101,102,103"
            rows = outward_nodes
        else:
            assert request.url.path.endswith("/map") and "bbox" in request.url.params
            rows = outward_nodes[:2] + return_nodes
        reads.append(request.url.path)
        xml = "".join(
            f'<node id="{r["id"]}" version="1" lat="{r["lat"]}" lon="{r["lon"]}"><tag k="highway" v="bus_stop"/><tag k="name" v="{r["tags"]["name"]}"/></node>'
            for r in rows
        )
        return httpx.Response(200, text=f"<osm>{xml}</osm>")

    def client():
        return httpx.AsyncClient(transport=httpx.MockTransport(api))

    monkeypatch.setattr(corridor, "get_public_client", client)
    monkeypatch.setattr(returning, "get_public_client", client)
    async with create_connected_server_and_client_session(mcp) as session:
        trips = []
        for trace in ([A, B, C], [C, B, A]):
            response = await session.call_tool(
                "suggest_bus_route_ways",
                {"points": [{"lat": lat, "lon": lon} for lat, lon in trace]},
            )
            trips.append(response.structuredContent["data"])
        review = await session.call_tool(
            "review_bus_return_trip",
            {
                "outward_stop_ids": [101, 102, 103],
                "outward_match": trips[0],
                "return_match": trips[1],
                "provider": "editing_api",
                "pair_radius_m": 25,
            },
        )
    assert review.structuredContent["success"]
    result = review.structuredContent["data"]
    visits = result["return_visits"]
    assert [v["node_id"] for v in visits if v["status"] == "candidate"] == [
        202,
        203,
        201,
    ]
    first, second, missing = result["outward_stops"]
    assert first["pair_status"] == second["pair_status"] == "candidate"
    assert missing["pair_status"] == "missing"
    link = next(r for r in first["nearby_return_visits"] if r["status"] == "candidate")
    assert (
        not link["same_name"] and not link["same_node"] and 10 < link["distance_m"] < 12
    )
    assert visits[link["return_visit_index"]]["name"] == "Local name"
    assert visits[link["return_visit_index"]]["osm_url"].endswith("/node/201")
    assert [
        visits[i]["node_id"] for i in result["unpaired_return_candidate_indices"]
    ] == [203]
    assert result["road_comparison"]["return"] == {
        "ways_only_in_this_direction": [],
        "turns_without_reverse_counterpart": [],
    }
    assert (
        result["road_comparison"]["matched_endpoints"]["outward_start_return_end"][
            "distance_m"
        ]
        == 0
    )
    assert (
        result["service_verified"] is False and result["return_input_kind"] == "trace"
    )
    assert len(reads) == 2


def test_changed_streets_and_junctions_preserve_return_order_and_skip_gap():
    outward_roads = [way(10, [1, 2], [A, B]), way(11, [2, 3], [B, C])]
    d = (38.522, 68.7611)
    outward = returning.BusTripMatch(**matcher._match_ways([A, B, C], outward_roads))
    return_roads = [
        way(20, [3, 4], [C, d]),
        way(10, [1, 2], [A, B]),
        way(21, [4, 2], [d, B]),
    ]
    back = returning.BusTripMatch(**matcher._match_ways([C, d, B, A], return_roads))
    diff = returning._road_differences(back, outward)
    assert [w["way_id"] for w in diff["ways_only_in_this_direction"]] == [20, 21]
    assert [
        (t["from_way_id"], t["via_node_id"], t["to_way_id"])
        for t in diff["turns_without_reverse_counterpart"]
    ] == [(20, 4, 21), (21, 2, 10)]
    # A journey can use a loop way in the same circulation direction on both
    # trips. Swapping way IDs alone would hide a different road approach.
    reverse_order = [
        p.model_copy(
            update={"start_node_id": p.end_node_id, "end_node_id": p.start_node_id}
        )
        for p in reversed(outward.traversals)
    ]
    changed_approach = outward.model_copy(update={"traversals": reverse_order})
    assert returning._road_differences(changed_approach, outward)[
        "turns_without_reverse_counterpart"
    ]
    split = [back.traversals[0], back.traversals[1].model_copy(update={"part": 1})]
    assert returning._turns(split) == []


def test_multiple_pairs_opposite_side_and_exclusions_are_reported():
    nodes = {
        i: stop(i, 0, lon, "")
        for i, lon in enumerate([0.001, 0.00105, 0.002, 0.003], 1)
    }
    visits = []
    for i, (lon, status, excluded) in enumerate(
        [
            (0.001, "candidate", False),
            (0.002, "opposite", False),
            (0.003, "candidate", True),
        ],
        1,
    ):
        visits.append(
            {
                "part": 0,
                "node_id": 10 + i,
                "name": "",
                "lat": 0,
                "lon": lon,
                "along_m": i,
                "distance_m": 1,
                "status": status,
                "excluded": excluded,
            }
        )
    corridor_data = {
        "candidates": visits[:1],
        "opposite": visits[1:2],
        "ambiguous": [],
        "excluded": visits[2:],
    }
    result = returning._pair_stops(list(nodes), nodes, corridor_data, 20)
    assert [s["pair_status"] for s in result["outward_stops"]] == [
        "ambiguous",
        "ambiguous",
        "opposite_side_only",
        "excluded_only",
    ]


@pytest.mark.asyncio
async def test_mismatched_map_target_or_parts_rejected_before_fetch(monkeypatch):
    trip = matcher._match_ways([A, B], [way(10, [1, 2], [A, B])])
    client = AsyncMock()
    monkeypatch.setattr(returning, "get_public_client", client)
    trip["matched_geojson"]["source"] = {"api_target": "another"}
    result = await returning.review_bus_return_trip([1], returning.BusTripMatch(**trip))
    assert not result["success"] and "target" in result["error"]
    del trip["matched_geojson"]["source"]
    trip["traversals"][0]["part"] = 2
    result = await returning.review_bus_return_trip([1], returning.BusTripMatch(**trip))
    assert not result["success"] and "part" in result["error"]
    client.assert_not_called()
