import asyncio
import time
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import httpx
import pytest

from src.osm_edit_mcp import track_tools

SIMPLE_GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Survey road</name><trkseg>
    <trkpt lat="41.0000" lon="44.0000"><time>2026-01-01T00:00:00Z</time></trkpt>
    <trkpt lat="41.0000" lon="44.0000"/>
    <trkpt lat="41.0001" lon="44.0001"><time>2026-01-01T00:01:00Z</time></trkpt>
    <trkpt lat="41.0002" lon="44.0002"><time>2026-01-01T00:02:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


@pytest.fixture(autouse=True)
def verified_osm_identity(monkeypatch):
    async def verify(client):
        return {
            "user_id": 123,
            "username": "test-mapper",
            "permissions": ["write_api"],
        }

    monkeypatch.setattr(track_tools, "verify_write_identity", verify)


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, get_responses=None, post_response=None):
        self.get_responses = get_responses or {}
        self.post_response = post_response
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        for suffix, response in self.get_responses.items():
            if url.endswith(suffix):
                return response
        return FakeResponse(404, "not found")

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_response or FakeResponse(500, "missing fake response")


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_unavailable_valhalla_returns_actionable_optional_failure(
    monkeypatch, error_type
):
    async def offline(*args, **kwargs):
        raise error_type("synthetic unavailable service")

    monkeypatch.setattr(
        track_tools,
        "_resolve_track_selection",
        lambda _: SimpleNamespace(points=[(1, 2), (1.1, 2.1)]),
    )
    monkeypatch.setattr(track_tools, "valhalla_match_track", offline)
    result = await track_tools.match_track_selection("test-selection")
    assert result["success"] is False
    assert result["error"] == error_type.__name__
    assert result["optional"] is True
    assert "OSM_VALHALLA_URL" in str(result["next_steps"])
    assert "suggest_track_road_candidates" in str(result["next_steps"])


@pytest.mark.asyncio
async def test_preview_without_identity_explains_auth_and_never_builds_proposal(
    monkeypatch,
):
    async def unauthenticated(client):
        raise PermissionError("Authentication required")

    async def forbidden_preview(*args, **kwargs):
        pytest.fail("A proposal must not be built without verified identity")

    client = FakeClient()
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)
    monkeypatch.setattr(track_tools, "verify_write_identity", unauthenticated)
    monkeypatch.setattr(track_tools, "_preview_create", forbidden_preview)
    result = await track_tools.preview_track_road_edit(
        action="create",
        changeset_comment="Synthetic test",
        changeset_source="survey",
        gpx_xml=SIMPLE_GPX,
        segment_id="trk-0-seg-0",
        tags={"highway": "service"},
    )
    assert result["success"] is False
    assert result["authentication_required"] is True
    assert "write_api" in result["message"]
    assert "preview_uri" in str(result["next_steps"])
    assert client.posts == []


class MapClient:
    def __init__(self, xml):
        self.xml = xml
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        return FakeResponse(text=self.xml)


class AcceptingContext:
    def __init__(self, proposal_digest):
        self.proposal_digest = proposal_digest
        self.message = None

    async def elicit(self, message, schema):
        self.message = message
        return SimpleNamespace(
            action="accept",
            data=track_tools.ApplyConfirmation(
                confirm=True,
                proposal_digest=self.proposal_digest,
            ),
        )


def capabilities_xml(waynodes=2000, changes=10000):
    return (
        '<osm><api><waynodes maximum="%s"/>'
        '<changesets maximum_elements="%s"/></api></osm>' % (waynodes, changes)
    )


def make_way(way_id, node_ids, coordinates, tags=None, version=3):
    nodes = {
        node_id: {
            "id": node_id,
            "lat": point[0],
            "lon": point[1],
            "version": 1,
            "tags": {},
        }
        for node_id, point in zip(node_ids, coordinates)
    }
    return {
        "id": way_id,
        "version": version,
        "node_ids": list(node_ids),
        "nodes": nodes,
        "tags": tags or {"highway": "residential"},
    }


@pytest.mark.asyncio
async def test_analyze_gpx_is_namespace_tolerant_and_deduplicates_points():
    result = await track_tools.analyze_gpx_track(gpx_xml=SIMPLE_GPX)

    assert result["success"] is True
    segment = result["data"]["segments"][0]
    assert segment["segment_id"] == "trk-0-seg-0"
    assert segment["point_count"] == 3
    assert segment["start_time"] == "2026-01-01T00:00:00Z"
    assert segment["end_time"] == "2026-01-01T00:02:00Z"


@pytest.mark.asyncio
async def test_analyze_requires_exactly_one_source():
    missing = await track_tools.analyze_gpx_track()
    both = await track_tools.analyze_gpx_track(gpx_xml=SIMPLE_GPX, gpx_path="track.gpx")

    assert missing["success"] is False
    assert both["success"] is False
    assert "exactly one" in missing["detail"]


@pytest.mark.asyncio
async def test_track_selection_crops_by_indexes_and_preserves_requested_direction():
    analysis = await track_tools.analyze_gpx_track(gpx_xml=SIMPLE_GPX)
    track_id = analysis["data"]["track_id"]

    forward = await track_tools.create_track_selection(
        track_id,
        "trk-0-seg-0",
        start_point_index=0,
        end_point_index=2,
    )
    reverse = await track_tools.create_track_selection(
        track_id,
        "trk-0-seg-0",
        start_point_index=2,
        end_point_index=0,
    )

    assert forward["success"] is True
    assert forward["data"]["point_count"] == 3
    forward_coordinates = forward["data"]["geojson"]["features"][0]["geometry"][
        "coordinates"
    ]
    reverse_coordinates = reverse["data"]["geojson"]["features"][0]["geometry"][
        "coordinates"
    ]
    assert reverse_coordinates == list(reversed(forward_coordinates))


@pytest.mark.asyncio
async def test_track_selection_rejects_discontinuous_subsection():
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="0" lon="0"/><trkpt lat="0" lon="0.001"/>
      <trkpt lat="1" lon="1"/>
    </trkseg></trk></gpx>"""
    analysis = await track_tools.analyze_gpx_track(gpx_xml=gpx)

    selected = await track_tools.create_track_selection(
        analysis["data"]["track_id"],
        "trk-0-seg-0",
        start_point_index=0,
        end_point_index=2,
    )

    assert selected["success"] is False
    assert "discontinuous" in selected["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gpx",
    [
        "<gpx><trk>",
        '<gpx><trk><trkseg><trkpt lat="91" lon="0"/></trkseg></trk></gpx>',
        '<gpx><trk><trkseg><trkpt lat="x" lon="0"/></trkseg></trk></gpx>',
    ],
)
async def test_analyze_rejects_malformed_or_invalid_gpx(gpx):
    result = await track_tools.analyze_gpx_track(gpx_xml=gpx)

    assert result["success"] is False


@pytest.mark.asyncio
async def test_preview_rejects_restricted_or_unapproved_imagery_sources():
    restricted = await track_tools.preview_track_road_edit(
        action="create",
        changeset_comment="Add road",
        changeset_source="survey",
        evidence_kind="permitted_imagery",
        evidence_provider="Yandex Maps",
        segment_id="trk-0-seg-0",
        gpx_xml=SIMPLE_GPX,
        tags={"highway": "residential"},
    )
    unapproved = await track_tools.preview_track_road_edit(
        action="create",
        changeset_comment="Add road",
        changeset_source="survey",
        evidence_kind="permitted_imagery",
        evidence_provider="Unknown Imagery",
        segment_id="trk-0-seg-0",
        gpx_xml=SIMPLE_GPX,
        tags={"highway": "residential"},
    )

    assert restricted["success"] is False
    assert "not permitted" in restricted["detail"]
    assert unapproved["success"] is False
    assert "OSM_PERMITTED_IMAGERY_SOURCES" in unapproved["detail"]


@pytest.mark.asyncio
async def test_discontinuous_history_can_be_analyzed_but_not_used_for_editing():
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="41" lon="44"/><trkpt lat="41.02" lon="44.02"/>
    </trkseg></trk></gpx>"""

    analysis = await track_tools.analyze_gpx_track(gpx_xml=gpx)
    candidates = await track_tools.suggest_track_road_candidates(
        segment_id="trk-0-seg-0", gpx_xml=gpx
    )
    preview = await track_tools.preview_track_road_edit(
        action="create",
        segment_id="trk-0-seg-0",
        changeset_comment="Add surveyed road",
        changeset_source="survey",
        gpx_xml=gpx,
        tags={"highway": "track"},
    )

    segment = analysis["data"]["segments"][0]
    assert analysis["success"] is True
    assert segment["discontinuity_count"] == 1
    assert any("crop or split" in warning for warning in segment["warnings"])
    assert candidates["success"] is False
    assert preview["success"] is False
    assert "discontinuous GPS" in candidates["detail"]


@pytest.mark.asyncio
async def test_limits_apply_to_bytes_and_raw_points(monkeypatch):
    monkeypatch.setattr(track_tools.config, "osm_track_max_file_bytes", 10)
    too_large = await track_tools.analyze_gpx_track(gpx_xml=SIMPLE_GPX)
    monkeypatch.setattr(track_tools.config, "osm_track_max_file_bytes", 10_000)
    monkeypatch.setattr(track_tools.config, "osm_track_max_points", 3)
    too_many_points = await track_tools.analyze_gpx_track(gpx_xml=SIMPLE_GPX)

    assert too_large["success"] is False
    # SIMPLE_GPX has four raw trkpt elements, even though one is a duplicate.
    assert too_many_points["success"] is False
    assert "track points" in too_many_points["detail"]


@pytest.mark.asyncio
async def test_track_path_is_restricted_to_import_directory(tmp_path, monkeypatch):
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    allowed = import_dir / "road.gpx"
    allowed.write_text(SIMPLE_GPX)
    outside = tmp_path / "outside.gpx"
    outside.write_text(SIMPLE_GPX)
    monkeypatch.setattr(track_tools.config, "osm_track_import_dir", import_dir)

    accepted = await track_tools.analyze_gpx_track(gpx_path="road.gpx")
    rejected = await track_tools.analyze_gpx_track(gpx_path=str(outside))

    assert accepted["success"] is True
    assert rejected["success"] is False
    assert "must stay inside" in rejected["detail"]


@pytest.mark.asyncio
async def test_symlink_cannot_escape_import_directory(tmp_path, monkeypatch):
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    outside = tmp_path / "outside.gpx"
    outside.write_text(SIMPLE_GPX)
    (import_dir / "escape.gpx").symlink_to(outside)
    monkeypatch.setattr(track_tools.config, "osm_track_import_dir", import_dir)

    result = await track_tools.analyze_gpx_track(gpx_path="escape.gpx")

    assert result["success"] is False
    assert "must stay inside" in result["detail"]


def test_simplification_preserves_endpoints():
    points = [(0.0, 0.0), (0.0, 0.00001), (0.0, 0.00002)]

    simplified = track_tools._simplify(points, 5.0)

    assert simplified == [points[0], points[-1]]


@pytest.mark.asyncio
async def test_nearby_highways_use_current_editing_api_map(monkeypatch):
    xml = """<osm>
      <node id="1" version="1" lat="41" lon="44"/>
      <node id="2" version="1" lat="41.001" lon="44.001"/>
      <node id="3" version="1" lat="41.002" lon="44.002"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><tag k="highway" v="track"/></way>
      <way id="20"><nd ref="2"/><nd ref="3"/><tag k="building" v="yes"/></way>
    </osm>"""
    client = MapClient(xml)
    monkeypatch.setattr(track_tools, "get_public_client", lambda: client)

    ways, nodes = await track_tools._nearby_highways(
        [(41.0, 44.0), (41.001, 44.001)], 30
    )

    assert [way["id"] for way in ways] == [10]
    assert set(nodes) == {1, 2}
    assert client.urls[0][0] == f"{track_tools.config.current_api_base_url}/map"


@pytest.mark.asyncio
async def test_candidate_suggestions_rank_and_preserve_explicit_selection(
    monkeypatch,
):
    ways = [
        {
            "type": "way",
            "id": 20,
            "nodes": [3, 4],
            "tags": {"highway": "service"},
            "geometry": [
                {"lat": 41.01, "lon": 44.01},
                {"lat": 41.02, "lon": 44.02},
            ],
        },
        {
            "type": "way",
            "id": 10,
            "nodes": [1, 2],
            "tags": {"highway": "residential"},
            "geometry": [
                {"lat": 41.0, "lon": 44.0},
                {"lat": 41.0002, "lon": 44.0002},
            ],
        },
    ]

    async def fake_nearby(points, radius):
        return ways, {}

    monkeypatch.setattr(track_tools, "_nearby_highways", fake_nearby)
    result = await track_tools.suggest_track_road_candidates(
        segment_id="trk-0-seg-0", gpx_xml=SIMPLE_GPX
    )

    assert result["success"] is True
    assert result["data"]["candidates"][0]["way_id"] == 10
    assert result["data"]["selection_required"] is True


@pytest.mark.asyncio
async def test_create_preview_requires_highway_tag(monkeypatch):
    async def fake_nearby(points, radius):
        return [], {}

    monkeypatch.setattr(track_tools, "_nearby_highways", fake_nearby)
    result = await track_tools.preview_track_road_edit(
        action="create",
        segment_id="trk-0-seg-0",
        changeset_comment="Add surveyed road",
        changeset_source="survey",
        gpx_xml=SIMPLE_GPX,
        tags={"surface": "gravel"},
    )

    assert result["success"] is False
    assert "highway=*" in result["detail"]


@pytest.mark.asyncio
async def test_create_preview_builds_geojson_and_expiring_proposal(
    monkeypatch,
):
    async def fake_nearby(points, radius):
        return [], {}

    client = FakeClient(
        get_responses={"/capabilities": FakeResponse(text=capabilities_xml())}
    )
    monkeypatch.setattr(track_tools, "_nearby_highways", fake_nearby)
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)

    result = await track_tools.preview_track_road_edit(
        action="create",
        segment_id="trk-0-seg-0",
        changeset_comment="Add surveyed road",
        changeset_source="survey",
        gpx_xml=SIMPLE_GPX,
        tags={"highway": "track", "surface": "gravel"},
    )

    assert result["success"] is True
    assert result["data"]["confirmation_required"] is True
    assert len(result["data"]["proposal_digest"]) == 64
    assert result["data"]["preview_uri"].startswith("ui://osm-edit/proposal/")
    assert result["data"]["operations"]["create_ways"][0]["tags"] == {
        "highway": "track",
        "surface": "gravel",
    }
    assert (
        result["data"]["proposed_geojson"]["features"][0]["geometry"]["type"]
        == "LineString"
    )
    assert result["data"]["expires_at_unix"] > time.time()
    preview_html = track_tools.proposal_preview_resource(result["data"]["proposal_id"])
    assert "<canvas" in preview_html
    assert "Current" in preview_html and "Proposed" in preview_html


@pytest.mark.asyncio
async def test_create_preview_inserts_shared_node_into_unambiguous_nearby_way(
    monkeypatch,
):
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="0.00005" lon="0.001"/>
      <trkpt lat="0.001" lon="0.001"/>
    </trkseg></trk></gpx>"""
    nearby_way = {
        "id": 10,
        "nodes": [1, 2],
        "tags": {"highway": "residential", "name": "Existing Road"},
        "geometry": [
            {"lat": 0.0, "lon": 0.0},
            {"lat": 0.0, "lon": 0.002},
        ],
    }
    full_way = """<osm>
      <node id="1" version="2" lat="0" lon="0"/>
      <node id="2" version="3" lat="0" lon="0.002"/>
      <way id="10" version="7"><nd ref="1"/><nd ref="2"/>
        <tag k="highway" v="residential"/><tag k="name" v="Existing Road"/>
      </way>
    </osm>"""

    async def fake_nearby(points, radius):
        return [nearby_way], {}

    client = FakeClient(
        get_responses={
            "/way/10/full": FakeResponse(text=full_way),
            "/capabilities": FakeResponse(text=capabilities_xml()),
        }
    )
    monkeypatch.setattr(track_tools, "_nearby_highways", fake_nearby)
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)

    result = await track_tools.preview_track_road_edit(
        action="create",
        segment_id="trk-0-seg-0",
        changeset_comment="Add connected surveyed road",
        changeset_source="survey",
        gpx_xml=gpx,
        tags={"highway": "service"},
        simplify_tolerance_m=0,
    )

    assert result["success"] is True
    assert result["data"]["summary"]["modified_ways"] == 1
    connection = result["data"]["endpoint_way_connections"][0]
    assert connection["endpoint"] == "start"
    assert connection["way_id"] == 10
    assert connection["status"] == "planned"
    assert result["data"]["dangling_endpoints"][0]["endpoint"] == "end"
    proposal = track_tools._PROPOSALS[result["data"]["proposal_id"]].payload
    shared_ref = proposal["create_ways"][0]["node_ids"][0]
    modified_way = proposal["modify_ways"][0]
    assert shared_ref < 0
    assert modified_way["node_ids"] == [1, shared_ref, 2]
    assert modified_way["tags"]["name"] == "Existing Road"
    assert proposal["snapshot_ways"]["10"]["version"] == 7
    assert result["data"]["current_geojson"]["features"]
    assert any(
        "insert a shared node" in warning for warning in result["data"]["warnings"]
    )

    osm_change = ET.fromstring(track_tools._build_osm_change(proposal, 123))
    created_way_refs = [
        int(node.get("ref")) for node in osm_change.findall("./create/way/nd")
    ]
    modified_way_refs = [
        int(node.get("ref")) for node in osm_change.findall("./modify/way/nd")
    ]
    assert shared_ref in created_way_refs
    assert shared_ref in modified_way_refs


@pytest.mark.asyncio
async def test_create_preview_blocks_ambiguous_endpoint_way_connection(monkeypatch):
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="0.00005" lon="0.001"/>
      <trkpt lat="0.001" lon="0.001"/>
    </trkseg></trk></gpx>"""
    ways = [
        {
            "id": 10,
            "nodes": [1, 2],
            "tags": {"highway": "residential"},
            "geometry": [
                {"lat": 0.0, "lon": 0.0},
                {"lat": 0.0, "lon": 0.002},
            ],
        },
        {
            "id": 20,
            "nodes": [3, 4],
            "tags": {"highway": "service"},
            "geometry": [
                {"lat": 0.0001, "lon": 0.0},
                {"lat": 0.0001, "lon": 0.002},
            ],
        },
    ]

    async def fake_nearby(points, radius):
        return ways, {}

    client = FakeClient(
        get_responses={"/capabilities": FakeResponse(text=capabilities_xml())}
    )
    monkeypatch.setattr(track_tools, "_nearby_highways", fake_nearby)
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)

    result = await track_tools.preview_track_road_edit(
        action="create",
        segment_id="trk-0-seg-0",
        changeset_comment="Add connected surveyed road",
        changeset_source="survey",
        gpx_xml=gpx,
        tags={"highway": "service"},
        simplify_tolerance_m=0,
    )

    assert result["success"] is False
    assert "ambiguously close" in result["data"]["blocking_issues"][0]
    connection = result["data"]["endpoint_way_connections"][0]
    assert connection["status"] == "ambiguous"
    assert connection["candidate_way_ids"] == [10, 20]


@pytest.mark.asyncio
async def test_update_preview_splices_contiguous_way_chain(monkeypatch):
    way_10 = make_way(
        10,
        [1, 2, 3],
        [(0.0, 0.0), (0.0, 0.001), (0.0, 0.002)],
        {"highway": "residential", "name": "Old Road"},
    )
    way_11 = make_way(
        11,
        [3, 4, 5],
        [(0.0, 0.002), (0.0, 0.003), (0.0, 0.004)],
        {"highway": "residential", "name": "Old Road"},
    )
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="0" lon="0"/><trkpt lat="0.0001" lon="0.001"/>
      <trkpt lat="0" lon="0.002"/><trkpt lat="0.0001" lon="0.003"/>
      <trkpt lat="0" lon="0.004"/>
    </trkseg></trk></gpx>"""

    async def fake_fetch(client, way_id):
        return way_10 if way_id == 10 else way_11

    async def fake_limits(client):
        return 2000, 10000

    async def unprotected(client, node):
        return False

    monkeypatch.setattr(track_tools, "_fetch_way_full", fake_fetch)
    monkeypatch.setattr(track_tools, "_fetch_api_limits", fake_limits)
    monkeypatch.setattr(track_tools, "_node_is_protected", unprotected)
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: FakeClient())

    result = await track_tools.preview_track_road_edit(
        action="update",
        segment_id="trk-0-seg-0",
        changeset_comment="Realign road from GPS survey",
        changeset_source="survey",
        gpx_xml=gpx,
        target_way_ids=[10, 11],
        simplify_tolerance_m=0,
    )

    assert result["success"] is True
    proposal = track_tools._PROPOSALS[result["data"]["proposal_id"]].payload
    assert [way["id"] for way in proposal["modify_ways"]] == [10, 11]
    assert proposal["modify_ways"][0]["tags"]["name"] == "Old Road"
    assert 3 in proposal["preserved_nodes"]
    assert {node["id"] for node in proposal["delete_nodes"]} == {2, 4}


@pytest.mark.asyncio
async def test_update_preview_handles_reversed_partial_track_and_protected_node(
    monkeypatch,
):
    way = make_way(
        10,
        [1, 2, 3, 4, 5],
        [
            (0.0, 0.0),
            (0.0, 0.001),
            (0.0, 0.002),
            (0.0, 0.003),
            (0.0, 0.004),
        ],
    )
    # Recorded in reverse, covering only node 4 back to node 2.
    gpx = """<gpx><trk><trkseg>
      <trkpt lat="0" lon="0.003"/><trkpt lat="0.00005" lon="0.002"/>
      <trkpt lat="0" lon="0.001"/>
    </trkseg></trk></gpx>"""

    async def fake_fetch(client, way_id):
        return way

    async def fake_limits(client):
        return 2000, 10000

    async def protect_middle(client, node):
        return node["id"] == 3

    monkeypatch.setattr(track_tools, "_fetch_way_full", fake_fetch)
    monkeypatch.setattr(track_tools, "_fetch_api_limits", fake_limits)
    monkeypatch.setattr(track_tools, "_node_is_protected", protect_middle)
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: FakeClient())

    result = await track_tools.preview_track_road_edit(
        action="update",
        segment_id="trk-0-seg-0",
        changeset_comment="Realign part of road",
        changeset_source="survey",
        gpx_xml=gpx,
        target_way_ids=[10],
        simplify_tolerance_m=0,
    )

    assert result["success"] is True
    proposal = track_tools._PROPOSALS[result["data"]["proposal_id"]].payload
    proposed_ids = proposal["modify_ways"][0]["node_ids"]
    assert proposed_ids[0] == 1
    assert proposed_ids[-1] == 5
    assert 3 in proposed_ids
    assert proposal["delete_nodes"] == []


def test_osm_change_uses_negative_ids_versions_and_conditional_deletes():
    payload = {
        "create_nodes": [{"id": -1, "lat": 1.0, "lon": 2.0, "tags": {}}],
        "create_ways": [
            {"id": -100, "node_ids": [5, -1], "tags": {"highway": "track"}}
        ],
        "modify_ways": [
            {"id": 9, "version": 4, "node_ids": [5, -1], "tags": {"name": "A&B"}}
        ],
        "delete_nodes": [{"id": 6, "version": 2, "lat": 1.1, "lon": 2.1}],
    }

    xml = track_tools._build_osm_change(payload, 123)
    root = ET.fromstring(xml)

    assert root.find("./create/node").get("id") == "-1"
    assert root.find("./modify/way").get("version") == "4"
    assert root.find("./delete").get("if-unused") == "true"
    assert root.find("./modify/way/tag").get("v") == "A&B"


@pytest.mark.asyncio
async def test_apply_requires_confirmation():
    result = await track_tools.apply_track_road_edit(
        "anything",
        "not-reviewed",
        confirm=False,
        context=AcceptingContext("not-reviewed"),
    )

    assert result["success"] is False
    assert result["error"] == "Confirmation required"


@pytest.mark.asyncio
async def test_compatibility_apply_requires_exact_digest():
    proposal = track_tools._store_proposal({"blocking_issues": []})

    result = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        "wrong-digest",
        confirm=True,
        context=AcceptingContext("wrong-digest"),
    )

    assert result["success"] is False
    assert result["error"] == "Proposal digest mismatch"


@pytest.mark.asyncio
async def test_compatibility_apply_always_uses_host_elicitation(monkeypatch):
    proposal = track_tools._store_proposal(
        {"blocking_issues": [], "summary": {"new_ways": 1}}
    )
    context = AcceptingContext(proposal.digest)

    async def fake_apply(proposal_id, proposal_digest, changeset_id=None):
        return {"success": True, "proposal_digest": proposal_digest}

    monkeypatch.setattr(track_tools, "_apply_osm_edit_internal", fake_apply)
    monkeypatch.setattr(track_tools.config, "osm_require_host_confirmation", False)

    result = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        proposal.digest,
        confirm=True,
        context=context,
    )

    assert result["success"] is True
    assert proposal.digest in context.message


@pytest.mark.asyncio
async def test_compatibility_apply_rejects_non_development_target(monkeypatch):
    monkeypatch.setattr(track_tools.config, "osm_use_dev_api", False)

    result = await track_tools.apply_track_road_edit(
        "anything",
        "not-reviewed",
        confirm=True,
        context=AcceptingContext("not-reviewed"),
    )

    assert result["success"] is False
    assert result["error"] == "Development API required"


@pytest.mark.asyncio
async def test_apply_rejects_expired_proposal():
    proposal = track_tools._store_proposal({"blocking_issues": []})
    proposal.expires_at = time.time() - 1

    result = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        proposal.digest,
        confirm=True,
        context=AcceptingContext(proposal.digest),
    )

    assert result["success"] is False
    assert result["error"] == "Unknown or expired proposal"


@pytest.mark.asyncio
async def test_version_validation_rejects_node_changed_after_preview():
    client = FakeClient(
        get_responses={
            "/node/5": FakeResponse(
                text='<osm><node id="5" version="2" lat="1" lon="2"/></osm>'
            )
        }
    )
    payload = {
        "snapshot_ways": {},
        "snapshot_nodes": {"5": {"version": 1}},
        "delete_nodes": [],
    }

    with pytest.raises(ValueError, match="changed after preview"):
        await track_tools._validate_proposal_versions(client, payload)


@pytest.mark.asyncio
async def test_version_validation_rejects_new_or_changed_highway_in_bbox(
    monkeypatch,
):
    payload = {
        "context_points": [(1.0, 2.0), (1.1, 2.1)],
        "context_radius_m": 30.0,
        "context_highways": {},
        "snapshot_ways": {},
        "snapshot_nodes": {},
        "delete_nodes": [],
    }

    async def changed_context(points, radius):
        return [
            {
                "id": 10,
                "version": 1,
                "nodes": [1, 2],
                "tags": {"highway": "service"},
            }
        ], {}

    monkeypatch.setattr(track_tools, "_nearby_highways", changed_context)

    with pytest.raises(ValueError, match="affected area changed"):
        await track_tools._validate_proposal_versions(FakeClient(), payload)


@pytest.mark.asyncio
async def test_owned_changeset_uses_structured_reserved_metadata():
    class PutClient:
        request = None

        async def put(self, url, **kwargs):
            self.request = (url, kwargs)
            return FakeResponse(text="77")

    client = PutClient()
    changeset_id = await track_tools._create_owned_changeset(
        client,
        {
            "changeset_comment": 'Add A&B "road"',
            "changeset_source": "survey & local knowledge",
        },
    )
    root = ET.fromstring(client.request[1]["content"])
    tags = {tag.get("k"): tag.get("v") for tag in root.findall(".//changeset/tag")}

    assert changeset_id == 77
    assert tags["comment"] == 'Add A&B "road"'
    assert tags["source"] == "survey & local knowledge"
    assert tags["created_by"].startswith("osm-edit-mcp/")


@pytest.mark.asyncio
async def test_apply_uploads_mocked_diff_and_closes_owned_changeset(monkeypatch):
    payload = {
        "action": "create",
        "track_hash": "abc",
        "segment_id": "trk-0-seg-0",
        "changeset_comment": "Add road",
        "changeset_source": "survey",
        "create_nodes": [
            {"id": -1, "lat": 1.0, "lon": 2.0, "tags": {}},
            {"id": -2, "lat": 1.1, "lon": 2.1, "tags": {}},
        ],
        "create_ways": [
            {"id": -100, "node_ids": [-1, -2], "tags": {"highway": "track"}}
        ],
        "modify_ways": [],
        "delete_nodes": [],
        "snapshot_ways": {},
        "snapshot_nodes": {},
        "warnings": [],
        "blocking_issues": [],
        "summary": {"new_nodes": 2, "new_ways": 1},
    }
    proposal = track_tools._store_proposal(payload)
    diff = """<diffResult generator="test" version="0.6">
      <node old_id="-1" new_id="101" new_version="1"/>
      <node old_id="-2" new_id="102" new_version="1"/>
      <way old_id="-100" new_id="201" new_version="1"/>
    </diffResult>"""
    client = FakeClient(post_response=FakeResponse(text=diff))

    async def fake_create(client, payload):
        return 77

    async def fake_close(client, changeset_id):
        return True

    async def fake_identity(client):
        return {"user_id": 123, "username": "test", "permissions": ["write_api"]}

    async def fake_verify(client, diff_results):
        return {"status": "verified", "verified": list(diff_results), "failures": []}

    monkeypatch.setattr(track_tools, "load_oauth_token", lambda: {"access_token": "x"})
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)
    monkeypatch.setattr(track_tools, "_create_owned_changeset", fake_create)
    monkeypatch.setattr(track_tools, "_close_owned_changeset", fake_close)
    monkeypatch.setattr(track_tools, "verify_write_identity", fake_identity)
    monkeypatch.setattr(track_tools, "_verify_diff_results", fake_verify)

    result = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        proposal.digest,
        confirm=True,
        context=AcceptingContext(proposal.digest),
    )

    assert result["success"] is True
    assert result["data"]["changeset_id"] == 77
    assert result["data"]["changeset_closed"] is True
    assert result["data"]["diff_results"][-1]["new_id"] == 201
    assert client.posts[0][0].endswith("/changeset/77/upload")


@pytest.mark.asyncio
async def test_concurrent_apply_never_uploads_the_same_proposal_twice(monkeypatch):
    payload = {
        "action": "create",
        "track_hash": "abc",
        "segment_id": "trk-0-seg-0",
        "changeset_comment": "Add road",
        "changeset_source": "survey",
        "create_nodes": [
            {"id": -1, "lat": 1.0, "lon": 2.0, "tags": {}},
            {"id": -2, "lat": 1.1, "lon": 2.1, "tags": {}},
        ],
        "create_ways": [
            {"id": -100, "node_ids": [-1, -2], "tags": {"highway": "track"}}
        ],
        "modify_ways": [],
        "delete_nodes": [],
        "snapshot_ways": {},
        "snapshot_nodes": {},
        "warnings": [],
        "blocking_issues": [],
        "summary": {"new_nodes": 2, "new_ways": 1},
    }
    proposal = track_tools._store_proposal(payload)
    diff = """<diffResult generator="test" version="0.6">
      <node old_id="-1" new_id="101" new_version="1"/>
      <node old_id="-2" new_id="102" new_version="1"/>
      <way old_id="-100" new_id="201" new_version="1"/>
    </diffResult>"""

    class YieldingClient(FakeClient):
        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            await asyncio.sleep(0.01)
            return FakeResponse(text=diff)

    client = YieldingClient()
    create_count = 0

    async def fake_create(client, payload):
        nonlocal create_count
        create_count += 1
        return 77

    async def fake_close(client, changeset_id):
        return True

    async def fake_identity(client):
        return {"user_id": 123, "username": "test", "permissions": ["write_api"]}

    async def fake_verify(client, diff_results):
        return {"status": "verified", "verified": list(diff_results), "failures": []}

    monkeypatch.setattr(track_tools, "load_oauth_token", lambda: {"access_token": "x"})
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)
    monkeypatch.setattr(track_tools, "_create_owned_changeset", fake_create)
    monkeypatch.setattr(track_tools, "_close_owned_changeset", fake_close)
    monkeypatch.setattr(track_tools, "verify_write_identity", fake_identity)
    monkeypatch.setattr(track_tools, "_verify_diff_results", fake_verify)

    results = await asyncio.gather(
        track_tools.apply_track_road_edit(
            proposal.proposal_id,
            proposal.digest,
            confirm=True,
            context=AcceptingContext(proposal.digest),
        ),
        track_tools.apply_track_road_edit(
            proposal.proposal_id,
            proposal.digest,
            confirm=True,
            context=AcceptingContext(proposal.digest),
        ),
    )

    assert len(client.posts) == 1
    assert create_count == 1
    assert sum(result["success"] for result in results) == 1


@pytest.mark.asyncio
async def test_transport_timeout_after_upload_requires_reconciliation(monkeypatch):
    payload = {
        "action": "create",
        "track_hash": "abc",
        "segment_id": "trk-0-seg-0",
        "changeset_comment": "Add road",
        "changeset_source": "survey",
        "create_nodes": [
            {"id": -1, "lat": 1.0, "lon": 2.0, "tags": {}},
            {"id": -2, "lat": 1.1, "lon": 2.1, "tags": {}},
        ],
        "create_ways": [
            {"id": -100, "node_ids": [-1, -2], "tags": {"highway": "track"}}
        ],
        "modify_ways": [],
        "delete_nodes": [],
        "snapshot_ways": {},
        "snapshot_nodes": {},
        "warnings": [],
        "blocking_issues": [],
        "summary": {"new_nodes": 2, "new_ways": 1},
    }
    proposal = track_tools._store_proposal(payload)

    class TimeoutClient(FakeClient):
        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            raise httpx.ReadTimeout("outcome unknown")

    client = TimeoutClient(
        get_responses={
            "/changeset/77/download": FakeResponse(
                text='<osmChange><create><way id="201" version="1"/></create></osmChange>'
            )
        }
    )

    async def fake_create(client, payload):
        return 77

    async def fake_close(changeset_id):
        return {"success": True}

    async def fake_identity(client):
        return {"user_id": 123, "username": "test", "permissions": ["write_api"]}

    monkeypatch.setattr(track_tools, "load_oauth_token", lambda: {"access_token": "x"})
    monkeypatch.setattr(track_tools, "get_authenticated_client", lambda: client)
    monkeypatch.setattr(track_tools, "_create_owned_changeset", fake_create)
    monkeypatch.setattr(track_tools, "close_changeset", fake_close)
    monkeypatch.setattr(track_tools, "verify_write_identity", fake_identity)

    result = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        proposal.digest,
        confirm=True,
        context=AcceptingContext(proposal.digest),
    )
    repeated = await track_tools.apply_track_road_edit(
        proposal.proposal_id,
        proposal.digest,
        confirm=True,
        context=AcceptingContext(proposal.digest),
    )

    assert result["success"] is False
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    assert result["reconciliation"]["status"] == "changeset_contains_elements"
    assert repeated["success"] is False
    assert len(client.posts) == 1


@pytest.mark.asyncio
async def test_apply_osm_edit_binds_host_confirmation_to_exact_digest(monkeypatch):
    proposal = track_tools._store_proposal(
        {"blocking_issues": [], "summary": {"new_ways": 1}}
    )

    class Confirmation:
        action = "accept"
        data = track_tools.ApplyConfirmation(
            confirm=True, proposal_digest=proposal.digest
        )

    class Context:
        message = None

        async def elicit(self, message, schema):
            self.message = message
            return Confirmation()

    context = Context()

    async def fake_apply(proposal_id, proposal_digest, changeset_id=None):
        return {
            "success": True,
            "data": {
                "proposal_id": proposal_id,
                "proposal_digest": proposal_digest,
            },
        }

    monkeypatch.setattr(track_tools, "_apply_osm_edit_internal", fake_apply)
    monkeypatch.setattr(track_tools.config, "osm_require_host_confirmation", True)

    result = await track_tools.apply_osm_edit(
        proposal.proposal_id, proposal.digest, context
    )

    assert result["success"] is True
    assert proposal.digest in context.message


@pytest.mark.asyncio
async def test_apply_osm_edit_fails_closed_when_host_cannot_elicit(monkeypatch):
    proposal = track_tools._store_proposal(
        {"blocking_issues": [], "summary": {"new_ways": 1}}
    )

    class Context:
        async def elicit(self, message, schema):
            raise RuntimeError("elicitation unsupported")

    monkeypatch.setattr(track_tools.config, "osm_require_host_confirmation", True)

    result = await track_tools.apply_osm_edit(
        proposal.proposal_id, proposal.digest, Context()
    )

    assert result["success"] is False
    assert result["error"] == "Host confirmation unavailable"
