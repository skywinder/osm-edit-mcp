"""Directional way proposals must retain order, topology and uncertainty."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from osm_edit_mcp import transit_match as tm


def way(way_id, ids, coordinates, **tags):
    return {
        "type": "way",
        "id": way_id,
        "version": 2,
        "nodes": ids,
        "geometry": [{"lat": lat, "lon": lon} for lat, lon in coordinates],
        "tags": {"highway": "primary", **tags},
    }


A, B, C = (0, 0), (0, 0.001), (0, 0.002)


def test_chain_covers_unobserved_connectors_and_partial_endpoints():
    d = (0, 0.003)
    ways = [way(6, [1, 2], [A, B]), way(2, [2, 3], [B, C]), way(8, [3, 4], [C, d])]
    result = tm._match_ways([(0, 0.0005), (0, 0.0025)], ways)
    assert result["ordered_way_ids"] == [6, 2, 8]
    assert result["gaps"] == []
    assert result["continuous"]
    assert result["diagnostics"]["split_review_way_ids"] == [6, 8]
    assert result["traversals"][0]["start_fraction"] == 0.5
    assert result["traversals"][-1]["end_fraction"] == 0.5


def test_reverse_oneway_and_psv_exception():
    w = way(1, [1, 2, 3], [A, B, C], oneway="yes")
    assert (
        tm._match_ways([C, A], [w])["gaps"][0]["reason"]
        == "no_connected_bus_path_near_survey"
    )
    w["tags"].update({"oneway:bus": "no", "access": "no", "psv": "designated"})
    result = tm._match_ways([C, A], [w])
    assert result["ordered_way_ids"] == [1]
    item = result["traversals"][0]
    assert (item["direction"], item["start_fraction"], item["end_fraction"]) == (
        "backward",
        1,
        0,
    )
    w["tags"]["bus:backward"] = "no"
    assert not tm._match_ways([C, A], [w])["continuous"]


def test_nonconsecutive_repeats_and_reversals_survive():
    ways = [way(10, [1, 2], [A, B]), way(20, [2, 3], [B, C])]
    result = tm._match_ways([A, B, C, C, B, A], ways)
    assert result["ordered_way_ids"] == [10, 20, 20, 10]
    assert [t["direction"] for t in result["traversals"]] == [
        "forward",
        "forward",
        "backward",
        "backward",
    ]


def test_no_jump_across_overpass_without_shared_osm_node():
    # Same XY at B, different node IDs and no connecting street.
    ways = [way(10, [1, 2], [A, B]), way(20, [9, 3], [B, C])]
    result = tm._match_ways([A, C], ways)
    assert result["ordered_way_ids"] == []
    assert result["gaps"] == [
        {
            "start_point_index": 0,
            "end_point_index": 1,
            "reason": "no_connected_bus_path_near_survey",
        }
    ]


def test_sparse_samples_split_output_and_do_not_download_the_gap():
    d, e = (0, 1), (0, 1.001)
    points = [A, B, d, e]
    result = tm._match_ways(points, [way(1, [1, 2], [A, B]), way(2, [3, 4], [d, e])])
    assert tm._query_chunks(points) == [[A, B], [d, e]]
    assert [item["part"] for item in result["traversals"]] == [0, 1]
    assert result["gaps"][0]["reason"] == "survey_points_over_500m_apart"
    assert not result["continuous"]


def test_close_parallel_roads_flag_ambiguity_but_pick_matching_oneway():
    parallel = [(0.00001, lon) for _, lon in [A, B]]
    roads = [
        way(1, [1, 2], [A, B], oneway="yes"),
        way(2, [3, 4], parallel, oneway="yes"),
    ]
    result = tm._match_ways([A, B], roads)
    assert result["ambiguous_point_indices"] == [0, 1]
    roads[0]["tags"]["oneway"] = "-1"
    assert tm._match_ways([A, B], roads)["ordered_way_ids"] == [2]


@pytest.mark.asyncio
async def test_review_and_replay_parallel_roads_rechecks_connectivity(monkeypatch):
    parallel = [(0.00001, lon) for _, lon in [A, B]]
    roads = [
        way(1, [1, 2], [A, B], oneway="yes"),
        way(2, [3, 4], parallel, name="Service road", oneway="yes"),
    ]
    monkeypatch.setattr(tm, "_load_highways", AsyncMock(return_value=(roads, {})))
    points = [tm.SurveyPoint(lat=lat, lon=lon) for lat, lon in [A, B]]
    first = (await tm.suggest_bus_route_ways(points=points))["data"]
    assert first["applied_snap_choices"] == [] and first["ordered_way_ids"] == [1]
    reviews = first["snap_reviews"]
    assert [r["point_index"] for r in reviews] == [0, 1]
    choices = []
    for index, r in enumerate(reviews):
        assert r["input_point"] == points[index].model_dump()
        assert r["candidate_count"] == 2
        automatic, alternate = r["candidates"]
        assert automatic["selected"] and not alternate["selected"]
        assert alternate["name"] == "Service road"
        assert alternate["allowed_directions"] == ["forward"]
        assert 1.1 < alternate["distance_m"] < 1.2
        assert alternate["snapped_point"] == {
            "lat": parallel[index][0],
            "lon": parallel[index][1],
        }
        assert alternate["segment_geometry"]["coordinates"] == [
            [lon, lat] for lat, lon in parallel
        ]
        choices.append(tm.SnapChoice(**alternate["choice"]))

    one = (await tm.suggest_bus_route_ways(points=points, snap_choices=choices[:1]))[
        "data"
    ]
    assert one["ambiguous_point_indices"] == [1]
    assert one["gaps"][0]["reason"] == "no_connected_bus_path_near_survey"
    assert not one["continuous"]
    both = (await tm.suggest_bus_route_ways(points=points, snap_choices=choices))[
        "data"
    ]
    assert both["ordered_way_ids"] == [2] and both["continuous"]
    assert both["ambiguous_point_indices"] == [] and both["requires_review"]
    assert both["applied_snap_choices"] == [c.model_dump() for c in choices]
    assert all(r["candidates"][1]["selected"] for r in both["snap_reviews"])


@pytest.mark.asyncio
async def test_reject_unusable_snap_choices_and_invalid_indices(monkeypatch):
    road = way(1, [1, 2, 3], [A, B, C])
    # A way can lose its bus access or a geometry node can move even when the
    # supplied version and structural segment identity appear correct.
    moved = way(2, [4, 5], [(0.001, 0), (0.001, 0.001)])
    denied = way(3, [6, 7], [A, B], bus="no")
    load = AsyncMock(return_value=([road, moved, denied], {}))
    monkeypatch.setattr(tm, "_load_highways", load)
    points = [tm.SurveyPoint(lat=lat, lon=lon) for lat, lon in [A, B]]
    choice = tm.SnapChoice(
        point_index=0,
        way_id=1,
        version=2,
        segment_index=0,
        start_node_id=1,
        end_node_id=2,
    )
    for update in (
        {"version": 1},
        {"start_node_id": 2, "end_node_id": 1},
        {"segment_index": 1},
        {"way_id": 2, "start_node_id": 4, "end_node_id": 5},
        {"way_id": 3, "start_node_id": 6, "end_node_id": 7},
    ):
        result = await tm.suggest_bus_route_ways(
            points=points, snap_choices=[choice.model_copy(update=update)]
        )
        assert not result["success"] and "Review fresh candidates" in result["error"]
    load.reset_mock()
    for invalid in (
        {"snap_choices": [choice, choice]},
        {"snap_choices": [choice.model_copy(update={"point_index": 2})]},
        {"review_point_indices": [0, 0]},
        {"review_point_indices": [2]},
    ):
        result = await tm.suggest_bus_route_ways(points=points, **invalid)
        assert (
            not result["success"]
            and result["error_details"]["code"] == "invalid_arguments"
        )
    load.assert_not_awaited()


def test_review_limits_and_requesting_specific_observations():
    # The close roads have distinct node IDs. Many repeated observations/ways
    # do not expand the default result beyond the documented candidate caps.
    roads = [
        way(i, [2 * i, 2 * i + 1], [A, B]) for i in range(1, tm.MAX_SNAP_CANDIDATES + 3)
    ]
    points = [A] * (tm.MAX_SNAP_REVIEWS + 1) + [B]
    first = tm._match_ways(points, roads)
    assert first["ambiguous_point_indices"] == list(range(len(points)))
    assert (
        len(first["snap_reviews"]) == tm.MAX_SNAP_REVIEWS
        and first["snap_reviews_omitted"] == 2
    )
    end = tm._match_ways(points, roads, review_point_indices=[len(points) - 1])
    (review,) = end["snap_reviews"]
    assert review["point_index"] == len(points) - 1 and end["snap_reviews_omitted"] == 0
    assert review["candidate_count"] == len(roads)
    assert len(review["candidates"]) == tm.MAX_SNAP_CANDIDATES
    # An explicit pick remains visible even below the default ranking cutoff.
    last = roads[-1]
    index = len(points) - 1
    pin = tm.SnapChoice(
        point_index=index,
        way_id=last["id"],
        version=2,
        segment_index=0,
        start_node_id=last["nodes"][0],
        end_node_id=last["nodes"][1],
    )
    pinned = tm._match_ways(
        points, roads, choices={index: pin}, review_point_indices=[index]
    )
    (selected,) = (c for c in pinned["snap_reviews"][0]["candidates"] if c["selected"])
    assert selected["choice"] == pin.model_dump()


def test_repeated_segment_identity_and_missing_metadata():
    repeated = way(10, [1, 2, 1, 2], [A, B, A, B])
    missing_version = way(11, [3, 4], [A, B])
    del missing_version["version"]
    initial = tm._match_ways(
        [A, B], [repeated, missing_version], review_point_indices=[0]
    )
    candidates = initial["snap_reviews"][0]["candidates"]
    assert [c["segment_index"] for c in candidates if c["way_id"] == 10] == [0, 1, 2]
    assert next(c for c in candidates if c["way_id"] == 11)["choice"] is None
    last_visit = next(
        c for c in candidates if c["way_id"] == 10 and c["segment_index"] == 2
    )
    choice = tm.SnapChoice(**last_visit["choice"])
    assert (choice.segment_index, choice.start_node_id, choice.end_node_id) == (2, 1, 2)
    pinned = tm._match_ways([A, B], [repeated, missing_version], choices={0: choice})
    (selected,) = (c for c in pinned["snap_reviews"][0]["candidates"] if c["selected"])
    assert selected["segment_index"] == 2


def test_review_retains_distinct_ways_when_nearest_way_has_many_segments():
    roads = [
        way(1, [1, 2] * 6, [A, B] * 6),
        way(2, [3, 4], [(0.00001, 0), (0.00001, 0.001)]),
        way(3, [5, 6], [(0.00015, 0), (0.00015, 0.001)]),
    ]
    review = tm._match_ways([A, B], roads, review_point_indices=[0])["snap_reviews"][0]
    assert (
        review["candidate_count"] > len(review["candidates"]) == tm.MAX_SNAP_CANDIDATES
    )
    assert {candidate["way_id"] for candidate in review["candidates"]} == {1, 2, 3}


@pytest.mark.asyncio
async def test_tool_selection_and_points_validation(monkeypatch):
    roads = [way(1, [1, 2], [A, B])]
    load = AsyncMock(return_value=(roads, {"provider": "fixture"}))
    monkeypatch.setattr(tm, "_load_highways", load)
    monkeypatch.setattr(
        tm, "_resolve_track_selection", lambda _: SimpleNamespace(points=[A, B])
    )
    selected = await tm.suggest_bus_route_ways(selection_id="local")
    assert selected["success"] and selected["data"]["selection_id"] == "local"
    points = [tm.SurveyPoint(lat=lat, lon=lon) for lat, lon in [A, B]]
    direct = await tm.suggest_bus_route_ways(points=points)
    assert direct["data"]["ordered_way_ids"] == [1]
    assert direct["data"]["source"]["provider"] == "fixture"
    for invalid in (
        {},
        {"points": points, "selection_id": "duplicate"},
        {"points": [points[0], points[0]]},
    ):
        assert not (await tm.suggest_bus_route_ways(**invalid))["success"]
    assert load.await_count == 2


def test_waypoints_infer_connected_legs_up_to_two_kilometers_only():
    c = (0, 0.009)
    e = (0, 0.03)
    points = [A, B, c, e]
    ways = [way(50, [1, 2, 3], points[:3])]
    result = tm._match_ways(points, ways, "waypoints")
    assert result["ordered_way_ids"] == [50]
    assert result["inferred_legs"] == [
        {"start_point_index": 0, "end_point_index": 1},
        {"start_point_index": 1, "end_point_index": 2},
    ]
    assert result["gaps"] == [
        {
            "start_point_index": 2,
            "end_point_index": 3,
            "reason": "waypoints_over_2000m_apart",
        }
    ]
    assert tm._query_chunks(points, "waypoints") == [points[:3]]
    assert tm._match_ways(points[:3], ways)["inferred_legs"] == []


@pytest.mark.asyncio
async def test_explicit_editing_api_uses_configured_target_and_no_overpass(monkeypatch):
    nearby = AsyncMock(return_value=([way(1, [1, 2], [A, B])], {}))
    overpass = AsyncMock()
    monkeypatch.setattr(tm, "_nearby_highways", nearby)
    monkeypatch.setattr(tm.overpass, "execute", overpass)
    roads, source = await tm._load_highways([A, B], "waypoints", "editing_api")
    assert source["provider"] == "OSM editing API" and [
        road["id"] for road in roads
    ] == [1]
    assert nearby.await_args.args == ([A, B], 300.0)
    overpass.assert_not_awaited()


def test_turn_at_interior_node_gives_exact_id_for_split_preview():
    q = (0.001, 0.001)
    ways = [way(1, [20, 21, 22], [A, B, C]), way(2, [21, 23], [B, q])]
    result = tm._match_ways([A, B, q], ways)
    assert result["ordered_way_ids"] == [1, 2]
    first, second = result["traversals"]
    assert first["end_fraction"] == 0.5 and first["interior_split_node_ids"] == [21]
    assert first["end_node_id"] == second["start_node_id"] == 21
    projected = tm._match_ways([(0, 0.0005), B, q], ways)["traversals"][0]
    assert projected["start_node_id"] is None and projected[
        "interior_split_node_ids"
    ] == [21]


def test_roundabout_crossing_node_order_seam_is_one_relation_member():
    base = (0, 0.002)
    west = (0, 0.001)
    north = (0.001, 0.002)
    south = (-0.001, 0.002)
    w = (0, 0)
    s = (-0.002, 0.002)
    ways = [
        way(10, [100, 1], [w, west]),
        way(
            20, [2, 3, 4, 1, 2], [base, south, north, west, base], junction="roundabout"
        ),
        way(30, [3, 101], [south, s]),
    ]
    result = tm._match_ways([w, west, base, south, s], ways)
    assert result["ordered_way_ids"] == [10, 20, 30]
    ring = result["traversals"][1]
    assert ring["roundabout_arc"] and not ring["requires_split_review"]
    assert ring["start_fraction"] > ring["end_fraction"]
    assert (ring["start_node_id"], ring["end_node_id"]) == (1, 3)


def test_geojson_clips_edges_and_separates_disconnected_parts(monkeypatch):
    end = (0, 0.004)
    points = [(0, 0.0005), B, C, (0, 0.0035)]
    # Two roads only, disconnected and each with independently clipped ends.
    roads = [way(1, [1, 2], [A, B]), way(2, [8, 9], [C, end])]
    result = tm._match_ways(points, roads)
    lines = result["matched_geojson"]["features"]
    assert result["geometry_omitted_reason"] is None and len(lines) == 2
    assert lines[0]["geometry"]["coordinates"] == [[0.0005, 0], [0.001, 0]]
    assert lines[1]["geometry"]["coordinates"] == [[0.002, 0], [0.0035, 0]]
    assert lines[1]["properties"]["bus_service_verified"] is False
    monkeypatch.setattr(tm, "MAX_PREVIEW_POINTS", 3)
    omitted = tm._match_ways(points, roads)
    assert (
        omitted["matched_geojson"] is None
        and "point" in omitted["geometry_omitted_reason"]
    )
    assert omitted["ordered_way_ids"] == result["ordered_way_ids"]
    monkeypatch.setattr(tm, "MAX_PREVIEW_POINTS", 4)
    monkeypatch.setattr(tm, "MAX_PREVIEW_BYTES", 20)
    assert "byte" in tm._match_ways(points, roads)["geometry_omitted_reason"]
