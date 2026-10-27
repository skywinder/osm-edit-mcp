"""Offline reviewed POI preview and map-context safety checks."""

from copy import deepcopy

import httpx
import pytest

from src.osm_edit_mcp import node_tools, track_tools
from src.osm_edit_mcp.proposal_store import ProposalStore, canonical_digest


@pytest.fixture
def node_create_client(monkeypatch, tmp_path):
    state = {"xml": '<osm version="0.6"/>', "requests": [], "full_xml": None}

    def handler(request):
        state["requests"].append(request)
        assert request.method == "GET", "Preview must never mutate OSM"
        assert "dev.openstreetmap.org" in str(request.url)
        if request.url.path.endswith("/full"):
            assert state["full_xml"] is not None
            return httpx.Response(200, text=state["full_xml"])
        assert request.url.path.endswith("/map")
        if isinstance(state["xml"], Exception):
            raise state["xml"]
        return httpx.Response(state.get("status", 200), text=state["xml"])

    async def identity(client):
        return {"user_id": 123, "username": "test-mapper", "permissions": ["write_api"]}

    async def limits(client):
        return 2000, 10000

    monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    monkeypatch.setattr(track_tools, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: None)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(
        track_tools, "_PROPOSAL_STORE", ProposalStore(tmp_path / "proposals.sqlite")
    )
    monkeypatch.setattr(
        track_tools,
        "get_authenticated_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return state


async def preview(**overrides):
    arguments = {
        "latitude": 27.332994,
        "longitude": 33.693731,
        "tags": {"shop": "supermarket"},
        "changeset_comment": "Add supermarket observed on site",
        "changeset_source": "survey",
    }
    arguments.update(overrides)
    return await node_tools.preview_node_create(**arguments)


@pytest.mark.asyncio
async def test_exact_readonly_durable_identity_bound_preview(node_create_client):
    result = await preview()
    assert result["success"], result
    data = result["data"]
    node = {
        "id": -1,
        "lat": "27.3329940",
        "lon": "33.6937310",
        "tags": {"shop": "supermarket"},
    }
    assert data["action"] == "node_create"
    assert data["osm_uid"] == 123
    assert data["confirmation_required"] is True
    assert data["segment_id"] is None and data["track_hash"] is None
    assert data["operations"] == {
        "create_nodes": [node],
        "create_ways": [],
        "modify_ways": [],
        "modify_nodes": [],
        "delete_nodes": [],
    }
    assert data["diff"] == {"before": None, "after": node}
    assert data["duplicate_search"]["status"] == "completed"
    assert data["duplicate_search"]["completed"] is True
    assert data["duplicate_search"]["possible_duplicate_count"] == 0
    assert data["duplicate_search"]["absence_proven"] is False
    assert data["duplicate_search"]["coverage_limitations"]
    assert data["current_geojson"]["features"] == []
    assert data["proposed_geojson"]["features"][0]["geometry"] == {
        "type": "Point",
        "coordinates": [33.693731, 27.332994],
    }
    assert len(node_create_client["requests"]) == 1
    track_tools._PROPOSALS.clear()
    proposal = track_tools._get_proposal(data["proposal_id"])
    assert proposal.digest == data["proposal_digest"]
    assert proposal.digest == canonical_digest(
        proposal.payload, proposal.api_target, 123
    )
    assert proposal.payload["context_snapshot"] == {
        "node": [],
        "way": [],
        "relation": [],
    }
    assert proposal.expires_at > proposal.created_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": True},
        {"longitude": False},
        {"latitude": "27.332994"},
        {"latitude": 90.0000001},
        {"latitude": -90.0000001},
        {"longitude": 180.0000001},
        {"longitude": -180.0000001},
        {"latitude": float("nan")},
        {"longitude": float("inf")},
        {"latitude": 27.33299401},
        {"longitude": 33.69373101},
        {"tags": {}},
        {"tags": {"shop": "supermarket", **{str(i): "v" for i in range(20)}}},
        {"tags": {"shop": None}},
        {"tags": {"shop": 1}},
        {"tags": {"shop": True}},
        {"tags": {"": "supermarket"}},
        {"tags": {"shop": ""}},
        {"tags": {"shop": "é" * 128}},
        {"tags": {"shop\x01": "supermarket"}},
        {"tags": {"shop": "supermarket\x00"}},
        {"tags": {"shop": "supermarket\x85"}},
        {"tags": {"name": "Example"}},
        {"tags": {"shop": "yes"}},
        {"tags": {"shop": "no"}},
        {"tags": {"shop": " no "}},
        {"tags": {"shop": " yes "}},
        {"tags": {"building": "retail"}},
        {"changeset_comment": " "},
        {"changeset_source": ""},
        {"changeset_comment": "x" * 256},
        {"changeset_source": "Google Maps"},
        {"changeset_source": "Yandex maps"},
        {"tags": {"shop": "supermarket", "source:name": "Google Maps"}},
    ],
)
async def test_invalid_input_fails_before_network_and_storage(
    node_create_client, overrides
):
    result = await preview(**overrides)
    assert result["success"] is False, result
    assert not track_tools._PROPOSALS
    assert node_create_client["requests"] == []


@pytest.mark.asyncio
async def test_auth_failure_never_attempts_map_lookup(node_create_client, monkeypatch):
    async def denied(client):
        raise PermissionError("OAuth write_api unavailable")

    monkeypatch.setattr(track_tools, "verify_write_identity", denied)
    result = await preview()
    assert not result["success"]
    assert not track_tools._PROPOSALS
    assert node_create_client["requests"] == []


POI_GEOMETRY_XML = """<osm version="0.6">
<node id="10" version="2" lat="27.332994" lon="33.693731">
<tag k="amenity" v="cafe"/><tag k="name" v="Different classification"/></node>
<node id="20" version="1" lat="27.332800" lon="33.693500"/>
<node id="21" version="1" lat="27.333100" lon="33.693500"/>
<node id="22" version="1" lat="27.333100" lon="33.693900"/>
<way id="30" version="4"><nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="20"/>
<tag k="shop" v="convenience"/><tag k="name" v="Existing shop"/></way>
<relation id="40" version="3"><member type="way" ref="30" role="outer"/>
<tag k="type" v="multipolygon"/><tag k="shop" v="supermarket"/></relation>
</osm>"""


@pytest.mark.asyncio
async def test_poi_nodes_ways_relations_and_different_classifications_block_apply(
    node_create_client,
):
    node_create_client["xml"] = POI_GEOMETRY_XML
    result = await preview()
    assert not result["success"]
    data = result["data"]
    candidates = data["duplicate_search"]["candidates"]
    assert [(item["type"], item["id"], item["version"]) for item in candidates] == [
        ("node", 10, 2),
        ("way", 30, 4),
        ("relation", 40, 3),
    ]
    assert candidates[0]["tags"] == {
        "amenity": "cafe",
        "name": "Different classification",
    }
    assert candidates[1]["geometry"]["type"] == "Polygon"
    assert candidates[2]["geometry"]["type"] == "GeometryCollection"
    assert [item["classification"] for item in candidates] == [
        "context_only",
        "context_only",
        "likely_duplicate",
    ]
    assert [item["blocking"] for item in candidates] == [False, False, True]
    assert data["duplicate_search"]["possible_duplicate_count"] == 1
    assert len(data["current_geojson"]["features"]) == 3
    assert data["blocking_issues"]
    proposal = track_tools._get_proposal(data["proposal_id"])
    async with track_tools.get_authenticated_client() as client:
        with pytest.raises(ValueError, match="unresolved"):
            await node_tools.validate_node_create_context(client, proposal.payload)
    assert len(node_create_client["requests"]) == 1


@pytest.mark.asyncio
async def test_other_classification_remains_visible_with_warning(node_create_client):
    node_create_client["xml"] = (
        '<osm><node id="10" version="2" lat="27.332994" lon="33.693731">'
        '<tag k="amenity" v="cafe"/></node></osm>'
    )
    result = await preview()
    assert result["success"], result
    search = result["data"]["duplicate_search"]
    assert search["possible_duplicate_count"] == 0
    assert search["candidates"][0]["blocking"] is False
    assert result["data"]["current_geojson"]["features"]
    assert any("Other nearby POIs" in warning for warning in result["data"]["warnings"])
    payload = track_tools._get_proposal(result["data"]["proposal_id"]).payload
    async with track_tools.get_authenticated_client() as client:
        await node_tools.validate_node_create_context(client, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("inside", [True, False])
async def test_only_containing_retail_area_blocks_new_shop(node_create_client, inside):
    node_create_client["xml"] = POI_GEOMETRY_XML.replace(
        '<tag k="shop" v="convenience"/>', '<tag k="building" v="retail"/>'
    ).replace('<tag k="shop" v="supermarket"/>', "")
    result = await preview(latitude=27.332994 if inside else 27.3327)
    assert result["success"] is not inside, result
    way = next(
        item
        for item in result["data"]["duplicate_search"]["candidates"]
        if item["type"] == "way"
    )
    assert way["blocking"] is inside


@pytest.mark.asyncio
async def test_remote_unicode_names_follow_osm_character_limit(node_create_client):
    node_create_client["xml"] = (
        '<osm><node id="10" version="2" lat="27.332994" lon="33.693731">'
        '<tag k="amenity" v="cafe"/><tag k="name" v="' + "ع" * 200 + '"/>'
        "</node></osm>"
    )
    result = await preview()
    assert result["success"], result
    assert (
        result["data"]["duplicate_search"]["candidates"][0]["tags"]["name"] == "ع" * 200
    )


@pytest.mark.asyncio
async def test_completes_poi_relation_geometry_using_configured_api(node_create_client):
    node_create_client["xml"] = (
        '<osm><relation id="40" version="3">'
        '<member type="way" ref="30" role="outer"/>'
        '<tag k="shop" v="supermarket"/></relation></osm>'
    )
    node_create_client["full_xml"] = """<osm>
<node id="20" version="1" lat="27.3328" lon="33.6935"/>
<node id="21" version="1" lat="27.3331" lon="33.6935"/>
<way id="30" version="4"><nd ref="20"/><nd ref="21"/></way>
<relation id="40" version="3"><member type="way" ref="30" role="outer"/>
<tag k="shop" v="supermarket"/></relation>
</osm>"""
    result = await preview()
    assert not result["success"]
    assert result["data"]["duplicate_search"]["status"] == "completed"
    assert (
        result["data"]["duplicate_search"]["candidates"][0]["geometry"]["geometries"][
            0
        ]["type"]
        == "LineString"
    )
    assert len(node_create_client["requests"]) == 2
    assert node_create_client["requests"][1].url.path.endswith("/relation/40/full")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "xml",
    [
        "<osm><node",
        "<error>upstream unavailable</error>",
        "<osm><remark>truncated</remark></osm>",
        '<osm><node id="10" version="1" lat="nan" lon="33"/></osm>',
        '<osm><node id="10" version="1" lat="91" lon="33"/></osm>',
        '<osm><node id="10" version="1" lat="27.000000000000001" lon="33"/></osm>',
        '<osm><node id="10" version="0" lat="27" lon="33"/></osm>',
        '<osm><node id="10" version="1" lat="27" lon="33" visible="false"/></osm>',
        '<osm><node id="10" version="1" lat="27" lon="33">'
        '<tag k="shop" v="cafe"/><tag k="shop" v="supermarket"/></node></osm>',
        '<osm><way id="10" version="1"><nd ref="1"/><nd ref="2"/></way></osm>',
        '<osm><relation id="10" version="1">'
        '<tag k="shop" v="supermarket"/></relation></osm>',
        '<osm><relation id="10" version="1">'
        '<member type="relation" ref="10" role=""/>'
        '<tag k="shop" v="supermarket"/></relation></osm>',
    ],
)
async def test_bad_or_incomplete_map_is_unknown_and_never_proves_absence(
    node_create_client, xml
):
    node_create_client["xml"] = xml
    result = await preview()
    assert not result["success"], result
    assert result["duplicate_search"]["status"] == "unknown"
    assert result["duplicate_search"]["completed"] is False
    assert "candidates" not in result["duplicate_search"]
    assert not track_tools._PROPOSALS


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout", "element_limit"])
async def test_failed_or_oversized_search_blocks_preview(
    node_create_client, monkeypatch, failure
):
    if failure == "http":
        node_create_client["status"] = 503
    elif failure == "timeout":
        node_create_client["xml"] = httpx.ReadTimeout("Map lookup timed out")
    else:
        monkeypatch.setattr(node_tools, "MAX_CONTEXT_ELEMENTS", 1)
        node_create_client["xml"] = (
            '<osm><node id="1" version="1" lat="27" lon="33"/>'
            '<node id="2" version="1" lat="27" lon="33"/></osm>'
        )
    result = await preview()
    assert not result["success"]
    assert result["duplicate_search"]["status"] == "unknown"
    assert not track_tools._PROPOSALS


@pytest.mark.asyncio
async def test_context_and_tags_are_covered_by_digest_and_freshness(node_create_client):
    node_create_client["xml"] = (
        '<osm><node id="99" version="1" lat="27.333" lon="33.6938">'
        '<tag k="building" v="yes"/></node></osm>'
    )
    result = await preview()
    assert result["success"]
    proposal = track_tools._get_proposal(result["data"]["proposal_id"])
    payload = proposal.payload
    async with track_tools.get_authenticated_client() as client:
        await node_tools.validate_node_create_context(client, payload)
    changed = deepcopy(payload)
    changed["context_snapshot"]["node"][0]["tags"]["building"] = "retail"
    assert canonical_digest(changed, proposal.api_target, 123) != proposal.digest
    node_create_client["xml"] = node_create_client["xml"].replace(
        'v="yes"', 'v="retail"'
    )
    async with track_tools.get_authenticated_client() as client:
        with pytest.raises(ValueError, match="changed"):
            await node_tools.validate_node_create_context(client, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "coordinate",
        "tag",
        "id",
        "extra_node",
        "way",
        "modify",
        "missing_context",
        "unknown_search",
        "radius",
        "bbox",
    ],
)
async def test_preapply_rejects_invalid_node_create_shape(node_create_client, mutation):
    data = (await preview())["data"]
    payload = track_tools._get_proposal(data["proposal_id"]).payload
    if mutation == "coordinate":
        payload["create_nodes"][0]["lat"] = "27.33299401"
    elif mutation == "tag":
        payload["create_nodes"][0]["tags"] = {"name": "Only a name"}
    elif mutation == "id":
        payload["create_nodes"][0]["id"] = -2
    elif mutation == "extra_node":
        payload["create_nodes"].append(deepcopy(payload["create_nodes"][0]))
    elif mutation == "way":
        payload["create_ways"] = [{"id": -2, "node_ids": [-1], "tags": {}}]
    elif mutation == "modify":
        payload["modify_nodes"] = [{"id": 10}]
    elif mutation == "missing_context":
        del payload["context_snapshot"]
    elif mutation == "unknown_search":
        payload["duplicate_search"]["status"] = "unknown"
    elif mutation == "radius":
        payload["duplicate_search"]["radius_m"] = 1
    else:
        payload["duplicate_search"]["bboxes"] = []
    async with track_tools.get_authenticated_client() as client:
        with pytest.raises(ValueError):
            await node_tools.validate_node_create_context(client, payload)
    assert len(node_create_client["requests"]) == 1


@pytest.mark.parametrize(
    "lat,lon", [(0, 180), (0, -180), (90, 0), (-90, 0), (27.332994, 33.693731)]
)
def test_duplicate_search_bbox_is_bounded_and_covers_extreme_coordinates(lat, lon):
    boxes = node_tools._context_bboxes(lat, lon)
    assert 1 <= len(boxes) <= 4
    parsed = [tuple(map(float, box.split(","))) for box in boxes]
    assert any(
        left <= lon <= right and bottom <= lat <= top
        for left, bottom, right, top in parsed
    )
    for left, bottom, right, top in parsed:
        assert -180 <= left < right <= 180
        assert -90 <= bottom < top <= 90
        assert (right - left) * (top - bottom) < 0.25
