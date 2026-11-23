"""Build a real route proposal from fixture map data and publish that exact review."""

import xml.etree.ElementTree as ET

import httpx
import pytest
from pydantic import ValidationError

from src.osm_edit_mcp import edit_tools, track_tools, transit_apply, transit_tools
from src.osm_edit_mcp.proposal_store import ProposalStore
from src.osm_edit_mcp.transit_data import (
    fetch_route_objects,
    restriction_snapshot,
    turn_issues,
)
from tests.test_transit_apply import Confirmation, RouteOSM


class SurveyOSM(RouteOSM):
    def way_xml(self):
        way = ET.fromstring(
            '<way id="7" version="3"><nd ref="101"/><nd ref="102"/><nd ref="103"/><tag k="highway" v="primary"/></way>'
        )
        return way

    def nodes_xml(self, ids):
        nodes = ET.Element("osm")
        for ref in ids:
            lat, lon = {
                101: (38.0, 68.0),
                102: (38.0, 68.001),
                103: (38.0, 68.002),
                201: (37.99995, 68.0),
                202: (37.99995, 68.002),
            }[ref]
            node = ET.SubElement(
                nodes,
                "node",
                id=str(ref),
                version=str(self.versions[ref]),
                lat=str(lat),
                lon=str(lon),
            )
            if ref in (201, 202):
                ET.SubElement(node, "tag", k="public_transport", v="platform")
                ET.SubElement(node, "tag", k="name", v="Народное имя")
        return nodes

    async def respond(self, req):
        if req.url.path.endswith("/ways"):
            return self.xml("osm", self.way_xml())
        if req.url.path.endswith("/nodes"):
            return httpx.Response(
                200,
                content=ET.tostring(
                    self.nodes_xml([int(s) for s in req.url.params["nodes"].split(",")])
                ),
            )
        if req.url.path.endswith("/map"):
            return httpx.Response(
                200, content=ET.tostring(self.nodes_xml(self.versions.keys() - {7}))
            )
        return await super().respond(req)


@pytest.mark.asyncio
async def test_candidate_to_preview_to_confirmation_to_readback(monkeypatch, tmp_path):
    api = SurveyOSM()
    store = ProposalStore(tmp_path / "state" / "proposals.sqlite")
    for module in (transit_tools, transit_apply):
        monkeypatch.setattr(module, "get_public_client", api.attach_client)
        monkeypatch.setattr(module, "get_authenticated_client", api.attach_client)

        async def identity(client):
            return {"user_id": api.uid}

        monkeypatch.setattr(module, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: {})
    locations = [
        transit_tools.SurveyStop(lat=37.99995, lon=68.0, label="A"),
        transit_tools.SurveyStop(lat=37.99995, lon=68.002, label="B"),
    ]
    found = await transit_tools.find_bus_route_stops(locations)
    assert found["success"], found
    stop_ids = [row["candidates"][0]["id"] for row in found["data"]["stops"]]
    args = dict(
        ref="1",
        from_name="A",
        to_name="B",
        way_ids=[7],
        stop_ids=stop_ids,
        source="test survey",
        omitted_stops=[
            transit_tools.OmittedStop(
                label="Old stop",
                reason="no longer served",
                location={"lat": 38.001, "lon": 68.003},
            ),
            transit_tools.OmittedStop(
                label="Former platform",
                reason="relocated",
                node_id=818,
                location={"lat": 38.0011, "lon": 68.0031},
            ),
            transit_tools.OmittedStop(
                label="Unlocated stop", reason="location unclear"
            ),
        ],
    )
    wrong_direction = await transit_tools.preview_bus_route(
        **{**args, "stop_ids": list(reversed(stop_ids))}, source_basis="survey"
    )
    assert not wrong_direction["success"]
    assert wrong_direction["data"]["blocking_issues"]
    blocked_features = wrong_direction["data"]["candidate_geojson"]["features"]
    assert len(blocked_features) == 5
    omitted_markers = [
        f for f in blocked_features if f["properties"].get("feature") == "omitted_stop"
    ]
    assert [f["geometry"]["coordinates"] for f in omitted_markers] == [
        [68.003, 38.001],
        [68.0031, 38.0011],
    ]
    assert [f["properties"]["label"] for f in omitted_markers] == [
        "Old stop",
        "Former platform",
    ]
    assert [f["properties"]["reason"] for f in omitted_markers] == [
        "no longer served",
        "relocated",
    ]
    assert "node_id" not in omitted_markers[0]["properties"]
    assert omitted_markers[1]["properties"]["node_id"] == 818
    assert all("stop_sequence" not in f["properties"] for f in omitted_markers)
    assert not store.list()
    inspect = await transit_tools.preview_bus_route(**args, prepare_upload=True)
    assert not inspect["success"] and "proposal_id" not in inspect["data"]
    assert not store.list()
    result = await transit_tools.preview_bus_route(
        **args, source_basis="survey", prepare_upload=True
    )
    assert result["success"], result
    data = result["data"]
    proposal_id = data["proposal_id"]
    assert [x["name"] for x in data["stops"]] == ["Народное имя"] * 2
    assert data["proposed_geojson"]["features"][0]["geometry"]["coordinates"] == [
        [68, 38],
        [68.001, 38],
        [68.002, 38],
    ]
    assert [
        f
        for f in data["proposed_geojson"]["features"]
        if f["properties"].get("feature") == "omitted_stop"
    ] == omitted_markers
    page = track_tools.proposal_preview_resource(proposal_id)
    assert "Old stop" in page and "Omitted stop locations</span>" in page
    assert not api.only_writes()
    digest = data["proposal_digest"]
    applied = await track_tools.apply_osm_edit(
        proposal_id, digest, Confirmation(digest)
    )
    assert applied["success"], applied
    assert (await edit_tools.verify_osm_edit(proposal_id))["success"]
    assert [
        (m.attrib["type"], int(m.attrib["ref"]), m.attrib["role"])
        for m in api.created.findall("member")
    ] == [("node", 201, "platform"), ("node", 202, "platform"), ("way", 7, "")]
    assert "Old stop" not in ET.tostring(api.created, encoding="unicode")


@pytest.mark.parametrize(
    "location",
    [
        {"lat": True, "lon": 0},
        {"lat": "38", "lon": 68},
        {"lat": 91, "lon": 68},
        {"lat": 38, "lon": 181},
        {"lat": 38, "lon": float("nan")},
        {"lat": 38},
    ],
)
def test_omission_locations_require_a_pair_of_numeric_geographic_coordinates(location):
    with pytest.raises(ValidationError):
        transit_tools.OmittedStop(
            label="Old stop", reason="relocated", location=location
        )


@pytest.mark.asyncio
async def test_live_bulk_read_rejects_incomplete_response():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<osm/>"))
    ) as client:
        with pytest.raises(ValueError, match="Incomplete"):
            await fetch_route_objects(client, [3], [4, 5])


@pytest.mark.parametrize(
    "rule,via,moves,exception,blocked",
    [
        ("no_left_turn", "node", [1, 3], "", True),
        ("no_left_turn", "node", [1, 2], "", False),
        ("no_left_turn", "node", [1, 3], "bus;bicycle", False),
        ("only_right_turn", "node", [1, 2], "", True),
        ("only_right_turn", "node", [1, 3], "", False),
        ("no_straight_on", "way", [1, 4, 3], "", True),
        ("no_straight_on", "way", [1, 4, 2], "", False),
        ("no_right_turn @ (Mo-Fr)", "node", [1, 3], "", True),
    ],
)
def test_turn_movements(rule, via, moves, exception, blocked):
    rel = ET.fromstring(
        '<relation id="17" version="4"><tag k="type" v="restriction"/><member type="way" role="from" ref="1"/><member type="way" role="to" ref="3"/></relation>'
    )
    ET.SubElement(
        rel,
        "tag",
        k="restriction:conditional" if "@" in rule else "restriction",
        v=rule,
    )
    ET.SubElement(rel, "tag", k="except", v=exception)
    ET.SubElement(rel, "member", type=via, role="via", ref="4" if via == "way" else "9")
    parents = {17: rel}
    traversals = [
        {"way_id": w, "from_node": 8 + i, "to_node": 9 + i} for i, w in enumerate(moves)
    ]
    assert bool(turn_issues(parents, traversals)) is blocked
    assert restriction_snapshot(parents) == ({} if exception else {"17": 4})


def test_only_turn_at_far_end_of_a_traversed_way():
    restriction = ET.fromstring(
        '<relation id="1" version="1"><tag k="type" v="restriction"/><tag k="restriction" v="only_right_turn"/><member type="way" ref="1" role="from"/><member type="way" ref="4" role="via"/><member type="way" ref="3" role="to"/></relation>'
    )
    via = {4: {"nodes": [100, 101]}}
    course = [{"way_id": 1, "to_node": 99}, {"way_id": 2, "to_node": 95}]
    assert not turn_issues({1: restriction}, course, via)
    course[0]["to_node"] = 100
    assert turn_issues({1: restriction}, course, via)
