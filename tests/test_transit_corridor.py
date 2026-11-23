from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from osm_edit_mcp import transit_corridor as c


def stop(identifier, lat, lon, role="platform", name=""):
    return dict(
        id=identifier,
        lat=lat,
        lon=lon,
        tags={"public_transport": role, "bus": "yes", "name": name},
    )


A, B, C = (0, 0), (0, 0.001), (0, 0.002)


def test_discovers_orders_local_names_and_opposing_platforms_without_names_as_input():
    items = [
        stop(2, -0.0001, 0.0016, name="Local"),
        stop(1, -0.0001, 0.0003, name="Other"),
        stop(3, 0.0001, 0.00165, name="Local"),
        stop(4, 0, 0.001, "stop_position"),
        stop(5, 0.001, 0.001),
    ]
    d = c._analyze_stops([A, B, C], items, "right", 35, set())
    assert [s["node_id"] for s in d["candidates"]] == [1, 2]
    assert d["candidates"][1]["name"] == "Local"
    assert d["candidates"][1]["nearby_same_name_opposite_node_ids"] == [3]
    assert d["opposite"][0]["node_id"] == 3 and d["ambiguous"][0]["node_id"] == 4
    assert d["ambiguous"][0]["role"] == "stop" and not d["service_verified"]
    left = c._analyze_stops([A, B, C], items, "left", 35, {3, 99})
    assert left["excluded_node_ids"] == [3, 99] and not left["candidates"]
    assert (
        left["excluded"][0]["node_id"] == 3
        and left["excluded"][0]["status"] == "candidate"
    )


def test_preserves_repeat_visits_and_keeps_opposite_direction_separate():
    item = stop(1, -0.0001, 0.0005)
    data = c._analyze_stops([A, B, C, B, A], [item], "right", 35, set())
    assert [s["node_id"] for s in data["candidates"]] == [1]
    assert [s["node_id"] for s in data["opposite"]] == [1]
    assert data["opposite"][0]["along_m"] > data["candidates"][0]["along_m"]


def test_gap_has_no_imaginary_stops_or_distance():
    path = [A, B, (0, 0.02), (0, 0.021)]
    items = [stop(1, -0.0001, 0.0005), stop(2, -0.0001, 0.01), stop(3, -0.0001, 0.0205)]
    data = c._analyze_stops(path, items, "right", 35, set())
    assert [(s["part"], s["node_id"]) for s in data["candidates"]] == [(0, 1), (1, 3)]
    assert data["gaps"][0]["start_point_index"] == 1 and data["part_count"] == 2
    assert 221 < data["covered_distance_m"] < 224


def test_endpoint_overshoot_and_corner_are_ambiguous():
    items = [stop(1, -0.00005, -0.00015), stop(2, -0.00004, 0.00104)]
    result = c._analyze_stops([A, B, (0.001, 0.001)], items, "right", 35, set())
    reasons = {i["node_id"]: i["reasons"] for i in result["ambiguous"]}
    assert "beyond_trace_endpoint" in reasons[1] and "near_sharp_turn" in reasons[2]
    assert not result["candidates"]


@pytest.mark.asyncio
async def test_api_node_fetch_dedupes_and_queries_windows_not_samples(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            request=request,
            text='<osm><node id="10" lat="-0.0001" lon="0.001"><tag k="highway" v="bus_stop"/></node><node id="100" lat="0" lon="0"><tag k="amenity" v="cafe"/></node></osm>',
        )

    monkeypatch.setattr(
        c,
        "get_public_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    points = [(0, i * 0.0002) for i in range(110)]
    monkeypatch.setattr(
        c, "_resolve_track_selection", lambda _: SimpleNamespace(points=points)
    )
    data = await c.suggest_bus_route_stops(selection_id="sel", provider="editing_api")
    assert data["success"] and len(calls) == data["data"]["source"]["map_windows"] == 2
    assert [x["node_id"] for x in data["data"]["candidates"]] == [10]
    assert all(
        r.url.path.endswith("/map") and list(r.url.params) == ["bbox"] for r in calls
    )


@pytest.mark.asyncio
async def test_oversparse_trace_is_reported_without_loading_map(monkeypatch):
    overpass = AsyncMock()
    monkeypatch.setattr(c.overpass, "execute", overpass)
    p = [c.SurveyPoint(lat=0, lon=0), c.SurveyPoint(lat=0, lon=0.01)]
    data = await c.suggest_bus_route_stops(points=p)
    assert (
        data["success"]
        and data["data"]["gaps"]
        and data["data"]["source"]["map_windows"] == 0
    )
    overpass.assert_not_awaited()
    for arg in (
        {},
        {"points": p, "selection_id": "both"},
        {"points": p, "radius_m": 101},
        {"points": p, "excluded_node_ids": [-1]},
    ):
        assert not (await c.suggest_bus_route_stops(**arg))["success"]


@pytest.mark.asyncio
async def test_public_overpass_uses_bboxes_and_closes_on_truncation(monkeypatch):
    monkeypatch.setattr(
        c,
        "config",
        SimpleNamespace(
            api_environment="production",
            current_api_base_url="https://api.openstreetmap.org/api/0.6",
        ),
    )
    query = AsyncMock(
        return_value={
            "elements": [stop(1, -0.0001, 0.001)],
            "osm3s": {"timestamp_osm_base": "sample"},
        }
    )
    monkeypatch.setattr(c.overpass, "execute", query)
    nodes, source = await c._stop_nodes([A, B, C], 35, "auto")
    assert (
        len(nodes) == 1
        and source["data_timestamp"] == "sample"
        and source["provider"] == "Overpass"
    )
    assert (
        "around" not in query.await_args.args[0]
        and "out body" in query.await_args.args[0]
    )
    monkeypatch.setattr(c, "MAX_NODES", 0)
    with pytest.raises(ValueError, match="Too many"):
        await c._stop_nodes([A, B], 35, "overpass")
