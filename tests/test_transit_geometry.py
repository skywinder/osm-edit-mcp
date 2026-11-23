"""Surveyed stops and road topology must identify a single bus traversal."""

import pytest

from osm_edit_mcp.transit_geometry import match_stop_candidates, validate_route_geometry


def node(ref, lat, lon, **tags):
    return {"type": "node", "id": ref, "lat": lat, "lon": lon, "tags": tags}


def road(ref, refs, **tags):
    return {
        "type": "way",
        "id": ref,
        "nodes": refs,
        "tags": {"highway": "residential", **tags},
    }


@pytest.fixture
def route():
    nodes = {
        i: node(i, 0, (i - 1) * 0.001, public_transport="stop_position", bus="yes")
        for i in range(1, 5)
    }
    nodes.update(
        {
            11: node(11, -0.0001, 0, highway="bus_stop", name="Local A"),
            12: node(12, -0.0001, 0.001, highway="bus_stop", name="Local B"),
            13: node(13, -0.0001, 0.003, public_transport="platform", bus="yes"),
            14: node(14, 0.0001, 0.001, highway="bus_stop", name="Local B"),
            15: node(15, 0, 0.001, public_transport="stop_position"),
            16: node(16, -0.002, 0.001, highway="bus_stop"),
        }
    )
    return {100: road(100, [1, 2]), 101: road(101, [4, 3, 2], oneway="-1")}, nodes


def test_contiguous_reversed_ways_and_local_names(route):
    ways, nodes = route
    result = validate_route_geometry([100, 101], [11, 12, 13], ways, nodes)
    assert [member["direction"] for member in result["traversals"]] == [
        "forward",
        "backward",
    ]
    assert result["node_ids"] == [1, 2, 3, 4]
    assert result["length_m"] == pytest.approx(333.6, abs=0.1)
    assert [n["role"] for n in result["stops"]] == ["platform"] * 3
    assert [n["distance_m"] for n in result["stops"]] == pytest.approx(
        [11.12] * 3, abs=0.01
    )
    assert nodes[11]["tags"]["name"] == "Local A"


@pytest.mark.parametrize(
    "ids, message",
    [
        ([11, 14, 13], "wrong side"),
        ([11, 16, 13], "too far"),
        ([11, 15, 13], "not a node"),
        ([12, 13], "must be split"),
        ([11, 3, 2, 13], "order"),
    ],
)
def test_wrong_side_distance_split_and_stop_order(route, ids, message):
    ways, nodes = route
    with pytest.raises(ValueError, match=message):
        validate_route_geometry([100, 101], ids, ways, nodes)


def test_exact_stop_then_its_platform(route):
    ways, nodes = route
    result = validate_route_geometry([100, 101], [1, 2, 12, 4], ways, nodes)
    assert [item["role"] for item in result["stops"]] == [
        "stop",
        "stop",
        "platform",
        "stop",
    ]
    assert result["stops"][1]["along_m"] == result["stops"][2]["along_m"]


def test_left_hand_traffic(route):
    ways, nodes = route
    result = validate_route_geometry(
        [100, 101], [1, 14, 4], ways, nodes, driving_side="left"
    )
    assert result["stops"][1]["id"] == 14


@pytest.mark.parametrize(
    "tags",
    [
        {"access": "private"},
        {"bus": "no", "psv": "yes"},
        {"psv:forward": "no"},
        {"bus:conditional": "yes @ (Mo-Fr)"},
        {"oneway": "-1"},
        {"oneway": "reversible"},
        {"highway": "footway", "access": "yes"},
        {"highway": "primary", "area": "yes"},
    ],
)
def test_bus_access_failures(route, tags):
    ways, nodes = route
    ways[100] = road(100, [1, 2], **tags)
    with pytest.raises(ValueError):
        validate_route_geometry([100, 101], [1, 4], ways, nodes)


def test_bus_specific_direction_and_access_override(route):
    ways, nodes = route
    ways[101] = road(
        101,
        [4, 3, 2],
        **{
            "oneway": "yes",
            "oneway:psv": "no",
            "access": "private",
            "bus": "designated",
        },
    )
    assert validate_route_geometry([100, 101], [1, 4], ways, nodes)["node_ids"] == [
        1,
        2,
        3,
        4,
    ]


def test_intersection_at_interior_requires_split(route):
    ways, nodes = route
    ways[100] = road(100, [1, 2, 3])
    nodes[5] = node(5, 0.01, 0.001, public_transport="stop_position")
    ways[101] = road(101, [2, 5])
    with pytest.raises(ValueError, match="split"):
        validate_route_geometry([100, 101], [1, 5], ways, nodes)


def test_roundabout_enters_and_exits_at_shared_interior_nodes(route):
    ways, nodes = route
    nodes.update({5: node(5, 0.0002, 0.0015), 6: node(6, -0.0002, 0.0015)})
    ways.update(
        {102: road(102, [5, 3, 6, 2, 5], junction="roundabout"), 101: road(101, [3, 4])}
    )
    result = validate_route_geometry([100, 102, 101], [1, 4], ways, nodes)
    assert result["node_ids"] == [1, 2, 5, 3, 4]
    assert result["traversals"][1] == {
        "way_id": 102,
        "from_node": 2,
        "to_node": 3,
        "direction": "forward",
    }


def test_repeated_way_valid_and_ambiguous_stop_visits(route):
    ways, nodes = route
    ways[101] = road(101, [2, 3, 4])
    ways[100] = road(100, [1, 2], oneway="yes")
    with pytest.raises(ValueError, match="multiple visits"):
        validate_route_geometry([100, 101, 101], [1, 3, 2], ways, nodes)
    result = validate_route_geometry([100, 101, 101], [1, 3, 4, 3, 2], ways, nodes)
    assert result["node_ids"] == [1, 2, 3, 4, 3, 2]
    assert result["traversals"][-1]["direction"] == "backward"


def test_candidates_keep_opposite_stops_at_same_distance_and_exclude_nonbus(route):
    _, nodes = route
    other = node(21, 0, 0.001, railway="platform", public_transport="platform")
    none = node(22, 0, 0.001, public_transport="platform", bus="no")
    matches = match_stop_candidates(
        0, 0.001, [nodes[14], nodes[12], nodes[12], other, none, nodes[16]]
    )
    assert [m["id"] for m in matches] == [12, 14]
    assert matches[0]["distance_m"] == matches[1]["distance_m"]


@pytest.mark.parametrize(
    "tags",
    [
        {"bus": "no"},
        {"access": "private"},
        {"bus:conditional": "yes @ (Mo-Fr)"},
        {"barrier": "gate", "locked": "yes", "access": "yes"},
        {"barrier": "bollard", "foot": "yes"},
        {"barrier": "block", "motor_vehicle": "yes"},
    ],
)
def test_traversed_node_can_block_bus(route, tags):
    ways, nodes = route
    nodes[2]["tags"] = tags
    with pytest.raises(ValueError, match="road node 2|Road node 2"):
        validate_route_geometry([100, 101], [1, 4], ways, nodes)


@pytest.mark.parametrize(
    "tags",
    [
        {"barrier": "bus_trap"},
        {"barrier": "bollard", "access": "no", "psv": "designated"},
        {"barrier": "lift_gate", "locked": "yes", "bus": "yes"},
    ],
)
def test_bus_permitted_at_barrier(route, tags):
    ways, nodes = route
    nodes[2]["tags"] = tags
    assert validate_route_geometry([100, 101], [1, 4], ways, nodes)["node_ids"] == [
        1,
        2,
        3,
        4,
    ]


@pytest.mark.parametrize("key", ["direction", "stop_position:direction"])
def test_directional_stop_on_repeated_way(route, key):
    ways, nodes = route
    ways[101] = road(101, [2, 3, 4])
    nodes[3]["tags"][key] = "backward"
    result = validate_route_geometry([100, 101, 101], [1, 3, 2], ways, nodes)
    assert result["stops"][1]["along_m"] > result["length_m"] / 2
    with pytest.raises(ValueError, match="direction"):
        validate_route_geometry([100, 101], [1, 3, 4], ways, nodes)


def test_stop_specific_direction_overrides_auxiliary_node_direction(route):
    ways, nodes = route
    nodes[3]["tags"].update(
        {
            "highway": "traffic_signals",
            "direction": "forward",
            "stop_position:direction": "backward",
        }
    )
    assert (
        validate_route_geometry([100, 101], [1, 3, 4], ways, nodes)["stops"][1]["id"]
        == 3
    )


def test_stop_direction_at_inconsistently_digitized_join_requires_review(route):
    ways, nodes = route
    nodes[2]["tags"]["direction"] = "forward"
    with pytest.raises(ValueError, match="ambiguous travel direction"):
        validate_route_geometry([100, 101], [1, 2, 4], ways, nodes)


@pytest.mark.parametrize("name", [None, "43 Микрорайон"])
def test_same_boarding_site_offset_is_one_call(route, name):
    ways, nodes = route
    ways[101] = road(101, [2, 3, 4])
    nodes[12] = node(12, -0.00008, 0.00098, public_transport="platform", bus="yes")
    if name:
        for ref in [2, 12]:
            nodes[ref]["tags"]["name"] = name
    result = validate_route_geometry([100, 101], [1, 2, 12, 4], ways, nodes)
    assert result["stops"][1]["along_m"] == result["stops"][2]["along_m"]
    nodes[2]["tags"]["name"] = "other station"
    nodes[12]["tags"]["name"] = "different station"
    with pytest.raises(ValueError, match="travel order"):
        validate_route_geometry([100, 101], [1, 2, 12, 4], ways, nodes)


def test_paired_stop_cannot_move_next_unrelated_call_earlier(route):
    ways, nodes = route
    ways[101] = road(101, [2, 3, 4])
    nodes[12] = node(12, -0.00008, 0.00098, public_transport="platform")
    nodes[17] = node(17, -0.00005, 0.00099, public_transport="platform", name="next")
    with pytest.raises(ValueError, match="travel order"):
        validate_route_geometry([100, 101], [1, 2, 12, 17, 4], ways, nodes)


@pytest.mark.parametrize("stop_ids,offset", [([1, 12], 0.00135), ([12, 2], -0.00035)])
def test_capped_projection_cannot_hide_terminus_overrun(route, stop_ids, offset):
    ways, nodes = route
    nodes[12] = node(12, -0.00005, offset, public_transport="platform")
    with pytest.raises(ValueError, match="Terminus"):
        validate_route_geometry([100], stop_ids, ways, nodes)


def test_terminal_lateral_offset_allowed_with_small_overrun(route):
    ways, nodes = route
    nodes[12] = node(12, -0.00025, 0.001045, public_transport="platform")
    result = validate_route_geometry([100], [1, 12], ways, nodes)
    assert result["stops"][-1]["along_m"] == result["length_m"]
