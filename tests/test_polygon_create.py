"""Strict four-sided POI creation, conversion, duplicate review and recovery."""

import json
import xml.etree.ElementTree as ET
from copy import deepcopy

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, polygon_tools, track_tools
from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.poi_duplicates import geometries_distance, review_candidates
from src.osm_edit_mcp.proposal_store import ProposalStore
from tests.test_node_create_apply import ConfirmationContext

TAGS = {"leisure": "pitch", "sport": "volleyball", "surface": "sand"}
CORNERS = [
    {"latitude": 27.243167, "longitude": 33.8442196},
    {"latitude": 27.243167, "longitude": 33.8443004},
    {"latitude": 27.243311, "longitude": 33.8443004},
    {"latitude": 27.243311, "longitude": 33.8442196},
]


def element(kind, attributes, tags=None, refs=None):
    node = ET.Element(kind, {k: str(v) for k, v in attributes.items()})
    for ref in refs or []:
        ET.SubElement(node, "nd", {"ref": str(ref)})
    for k, v in (tags or {}).items():
        ET.SubElement(node, "tag", {"k": k, "v": v})
    return node


def xml(root, *children):
    document = ET.Element(root)
    document.extend(children)
    return ET.tostring(document, encoding="unicode")


class PolygonAPI:
    def __init__(self):
        self.requests = []
        self.source = False
        self.source_version = 2
        self.parent_ways = False
        self.parent_relations = False
        self.parent_status = 200
        self.map_extra = ""
        self.map_error = None
        self.way_limit = 2000
        self.server_limit = 10000
        self.created = []
        self.deleted = False
        self.skip_delete = False
        self.upload_error = None
        self.apply_before_error = True
        self.tamper = None
        self.download_override = None
        self.diff_override = None

    @property
    def writes(self):
        return [r for r in self.requests if r.method != "GET"]

    @property
    def uploads(self):
        return [r for r in self.requests if r.method == "POST"]

    def source_element(self):
        return element(
            "node",
            {
                "id": 900,
                "version": self.source_version,
                "lat": "27.2432390",
                "lon": "33.8442600",
                "visible": "true",
                "changeset": 50,
            },
            TAGS,
        )

    def full(self):
        created = deepcopy(self.created)
        way = created[-1]
        if self.tamper == "way_tags":
            way.findall("tag")[0].set("v", "swimming_pool")
        elif self.tamper == "closure":
            way.findall("nd")[-1].set("ref", "202")
        elif self.tamper == "order":
            way.findall("nd")[1].set("ref", "203")
        elif self.tamper == "moved_corner":
            created[0].set("lat", "27.2431000")
        elif self.tamper == "tagged_vertex":
            ET.SubElement(created[0], "tag", {"k": "leisure", "v": "pitch"})
        elif self.tamper == "missing_corner":
            created.pop(0)
        elif self.tamper == "way_version":
            way.set("version", "2")
        elif self.tamper == "way_changeset":
            way.set("changeset", "99")
        return xml("osm", *created)

    def download(self):
        if self.download_override is not None:
            return self.download_override
        root = ET.Element("osmChange")
        section = ET.SubElement(root, "create")
        section.extend(deepcopy(self.created))
        if self.deleted:
            deletion = ET.SubElement(root, "delete")
            deletion.append(
                element(
                    "node",
                    {
                        "id": 900,
                        "version": self.source_version + 1,
                        "changeset": 77,
                        "visible": "false",
                    },
                )
            )
        return ET.tostring(root, encoding="unicode")

    def commit(self, request):
        root = ET.fromstring(request.content)
        mapping = {-1: 201, -2: 202, -3: 203, -4: 204, -1000000: 301}
        self.created = []
        diff = ET.Element("diffResult")
        for original in root.find("create"):
            node = deepcopy(original)
            old = int(node.attrib["id"])
            node.set("id", str(mapping[old]))
            node.set("version", "1")
            node.set("visible", "true")
            for ref in node.findall("nd"):
                ref.set("ref", str(mapping[int(ref.attrib["ref"])]))
            self.created.append(node)
            ET.SubElement(
                diff,
                node.tag,
                {"old_id": str(old), "new_id": str(mapping[old]), "new_version": "1"},
            )
        deletion = root.find("delete")
        if deletion is not None:
            assert (
                deletion.attrib == {}
            ), "Conversion must fail atomically if the source gains a parent"
            assert len(deletion) == 1 and deletion[0].get("id") == "900"
            self.deleted = not self.skip_delete
            if self.deleted:
                ET.SubElement(diff, "node", {"old_id": "900"})
        return ET.tostring(diff, encoding="unicode")

    async def handle(self, request):
        assert config.is_development_api, "Tests must never write production"
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.endswith("/map"):
            if self.map_error:
                return httpx.Response(200, text=self.map_error)
            data = (
                ET.tostring(self.source_element(), encoding="unicode")
                if self.source and not self.deleted
                else ""
            )
            return httpx.Response(200, text=f"<osm>{data}{self.map_extra}</osm>")
        if request.method == "GET" and path.endswith("/node/900"):
            return httpx.Response(200, text=xml("osm", self.source_element()))
        if request.method == "GET" and path.endswith(
            ("/node/900/ways", "/node/900/relations")
        ):
            kind = "way" if path.endswith("ways") else "relation"
            has_parent = self.parent_ways if kind == "way" else self.parent_relations
            return httpx.Response(
                self.parent_status,
                text=(
                    xml("osm", element(kind, {"id": 10, "version": 1}))
                    if has_parent
                    else "<osm/>"
                ),
            )
        if request.method == "GET" and path.endswith("/node/900/history"):
            history = [self.source_element()]
            if self.deleted:
                history.append(
                    element(
                        "node",
                        {
                            "id": 900,
                            "version": self.source_version + 1,
                            "changeset": 77,
                            "visible": "false",
                        },
                    )
                )
            return httpx.Response(200, text=xml("osm", *history))
        if request.method == "GET" and path.endswith("/way/301/full"):
            return httpx.Response(200, text=self.full())
        if request.method == "GET" and path.endswith("/changeset/77/download"):
            return httpx.Response(200, text=self.download())
        if request.method == "PUT" and path.endswith("/changeset/create"):
            return httpx.Response(200, text="77")
        if request.method == "PUT" and path.endswith("/changeset/77/close"):
            return httpx.Response(200)
        if request.method == "POST" and path.endswith("/changeset/77/upload"):
            diff = (
                self.commit(request)
                if not self.upload_error or self.apply_before_error
                else ""
            )
            if self.upload_error:
                raise self.upload_error
            return httpx.Response(200, text=self.diff_override or diff)
        raise AssertionError(f"Unexpected offline request {request.method} {path}")


@pytest.fixture
def polygon_workflow(monkeypatch, tmp_path):
    api = PolygonAPI()
    store = ProposalStore(tmp_path / "proposals.sqlite")

    def client():
        return httpx.AsyncClient(transport=httpx.MockTransport(api.handle))

    async def identity(client):
        return {"user_id": 123, "username": "offline", "permissions": ["write_api"]}

    async def limits(client):
        return api.way_limit, api.server_limit

    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(track_tools, "get_authenticated_client", client)
    monkeypatch.setattr(edit_tools, "get_public_client", client)
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: None)
    monkeypatch.setattr(track_tools, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    monkeypatch.setattr(
        track_tools, "load_oauth_token", lambda: {"access_token": "offline-test"}
    )
    return api, store


async def preview(**overrides):
    args = {
        "corners": deepcopy(CORNERS),
        "tags": dict(TAGS),
        "changeset_comment": "Demonstrate a four-sided volleyball area on dev",
        "changeset_source": "synthetic demonstration geometry; not surveyed",
        "demonstration": True,
    }
    args.update(overrides)
    return await polygon_tools.preview_poi_polygon_create(**args)


async def apply(data, context=None, **kwargs):
    return await track_tools.apply_osm_edit(
        data["proposal_id"],
        data["proposal_digest"],
        context or ConfirmationContext(data["proposal_digest"]),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_four_sides_are_a_closed_way_with_tags_only_on_area(polygon_workflow):
    api, store = polygon_workflow
    result = await preview()
    assert result["success"], result
    data = result["data"]
    assert data["summary"]["sides"] == 4
    assert data["summary"]["created_ways"] == 1
    assert data["summary"]["element_operations"] == 5
    assert data["proposed_geojson"]["features"][0]["geometry"]["type"] == "Polygon"
    assert data["operations"]["create_ways"] == [
        {"id": -1000000, "node_ids": [-1, -2, -3, -4, -1], "tags": TAGS}
    ]
    assert all(n["tags"] == {} for n in data["operations"]["create_nodes"])
    assert len(api.writes) == 0
    html = track_tools.proposal_preview_resource(data["proposal_id"])
    assert "Proposed polygon" in html and "SYNTHETIC DEMONSTRATION" in html
    applied = await apply(data)
    assert applied["success"], applied
    assert applied["data"]["way_id"] == 301
    assert applied["data"]["corner_node_ids"] == [201, 202, 203, 204]
    assert applied["data"]["verification"]["closed"] is True
    assert store.get(data["proposal_id"]).status == "APPLIED"
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert verified["success"] and verified["data"]["way_id"] == 301
    assert (await apply(data))["success"]
    assert len(api.uploads) == 1


@pytest.mark.asyncio
async def test_isolated_point_converts_atomically_to_polygon_without_duplicate(
    polygon_workflow,
):
    api, store = polygon_workflow
    api.source = True
    result = await preview(replace_node_id=900, expected_node_version=2)
    assert result["success"], result
    data = result["data"]
    assert data["operations"]["delete_nodes"][0]["id"] == 900
    assert data["summary"]["element_operations"] == 6
    source = data["duplicate_search"]["candidates"][0]
    assert source["classification"] == "likely_duplicate"
    assert source["replacement_source"] is True and source["blocking"] is False
    assert "Source point replaced by polygon" in track_tools.proposal_preview_resource(
        data["proposal_id"]
    )
    context = ConfirmationContext(data["proposal_digest"])
    result = await apply(data, context)
    assert result["success"], result
    assert "'deleted_nodes': [900]" in context.messages[0]
    assert api.deleted
    assert result["data"]["replaced_node_id"] == 900
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert (await edit_tools.verify_osm_edit(data["proposal_id"]))["success"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corners",
    [
        CORNERS[:3],
        CORNERS + [CORNERS[0]],
        CORNERS[:3] + [CORNERS[0]],
        [CORNERS[0], CORNERS[2], CORNERS[1], CORNERS[3]],
        [{"latitude": 27.0, "longitude": 33 + i * 0.00001} for i in range(4)],
        [{**CORNERS[0], "latitude": True}] + CORNERS[1:],
        [{**CORNERS[0], "latitude": "27.243167"}] + CORNERS[1:],
        [{**CORNERS[0], "longitude": 33.84421961}] + CORNERS[1:],
        [{**CORNERS[0], "extra": 1}] + CORNERS[1:],
        [
            {"latitude": 86 + i * 0.00001, "longitude": 33 + (i % 2) * 0.00001}
            for i in range(4)
        ],
        [
            {"latitude": 0, "longitude": 0},
            {"latitude": 0, "longitude": 1},
            {"latitude": 1, "longitude": 1},
            {"latitude": 1, "longitude": 0},
        ],
    ],
)
async def test_invalid_contours_fail_before_any_osm_read_or_write(
    polygon_workflow, corners
):
    api, _ = polygon_workflow
    result = await preview(corners=corners)
    assert not result["success"]
    assert not api.requests


@pytest.mark.asyncio
async def test_synthetic_geometry_is_dev_only_and_must_be_labelled(
    polygon_workflow, monkeypatch
):
    api, _ = polygon_workflow
    assert not (await preview(changeset_source="survey"))["success"]
    assert not (await preview(demonstration=False))["success"]
    monkeypatch.setattr(config, "osm_use_dev_api", False)
    result = await preview()
    assert not result["success"] and "dev API" in result["detail"]
    assert api.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attribute", ["parent_ways", "parent_relations", "parent_status", "source_version"]
)
async def test_replacement_needs_current_isolated_source(polygon_workflow, attribute):
    api, _ = polygon_workflow
    api.source = True
    setattr(
        api,
        attribute,
        (
            503
            if attribute == "parent_status"
            else 3 if attribute == "source_version" else True
        ),
    )
    result = await preview(replace_node_id=900, expected_node_version=2)
    assert not result["success"]
    assert api.writes == []


@pytest.mark.asyncio
async def test_replacement_cannot_discard_tags_or_target_an_outside_point(
    polygon_workflow,
):
    api, _ = polygon_workflow
    api.source = True
    assert not (
        await preview(
            replace_node_id=900,
            expected_node_version=2,
            tags={**TAGS, "name": "invented"},
        )
    )["success"]
    shifted = [{**c, "latitude": round(c["latitude"] + 0.001, 7)} for c in CORNERS]
    assert not (
        await preview(replace_node_id=900, expected_node_version=2, corners=shifted)
    )["success"]
    assert api.writes == []


def test_crossing_polygons_without_contained_vertices_still_overlap():
    horizontal = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0.0004], [0.001, 0.0004], [0.001, 0.0006], [0, 0.0006], [0, 0.0004]]
        ],
    }
    vertical = {
        "type": "Polygon",
        "coordinates": [
            [[0.0004, 0], [0.0006, 0], [0.0006, 0.001], [0.0004, 0.001], [0.0004, 0]]
        ],
    }
    assert geometries_distance(horizontal, vertical) == 0
    item = review_candidates(
        [
            {
                "type": "way",
                "id": 55,
                "version": 1,
                "tags": {"leisure": "pitch", "sport": "tennis"},
                "geometry": vertical,
            }
        ],
        {"lat": "0.0005", "lon": "0.0005", "tags": TAGS, "geometry": horizontal},
    )[0]
    assert item["classification"] == "likely_duplicate" and item["blocking"]


@pytest.mark.asyncio
async def test_same_point_blocks_new_area_without_explicit_conversion(polygon_workflow):
    api, _ = polygon_workflow
    api.source = True
    result = await preview()
    assert not result["success"]
    data = result["data"]
    rejected = await polygon_tools.review_poi_polygon_duplicates(
        data["proposal_id"], data["proposal_digest"], []
    )
    assert not rejected["success"]
    decision = {
        "osm_type": "node",
        "osm_id": 900,
        "expected_version": 2,
        "decision": "same_object",
        "reason": "Same physical court; convert the node instead",
        "evidence_source": "user report",
    }
    reviewed = await polygon_tools.review_poi_polygon_duplicates(
        data["proposal_id"], data["proposal_digest"], [decision]
    )
    assert not reviewed["success"] and reviewed["data"]["blocking_issues"]
    assert not (await apply(reviewed["data"]))["success"]
    assert api.writes == []


@pytest.mark.asyncio
async def test_false_match_review_creates_new_digest_and_retires_old_polygon(
    polygon_workflow,
):
    api, store = polygon_workflow
    api.map_extra = '<node id="999" version="1" lat="27.243239" lon="33.84436"><tag k="leisure" v="pitch"/><tag k="sport" v="tennis"/></node>'
    original = (await preview())["data"]
    decision = {
        "osm_type": "node",
        "osm_id": 999,
        "expected_version": 1,
        "decision": "distinct_object",
        "reason": "Separate adjacent tennis court",
        "evidence_source": "user report",
    }
    result = await polygon_tools.review_poi_polygon_duplicates(
        original["proposal_id"], original["proposal_digest"], [decision]
    )
    assert result["success"], result
    data = result["data"]
    assert data["proposal_digest"] != original["proposal_digest"]
    assert store.get(original["proposal_id"]).status == "SUPERSEDED"
    assert not (await apply(original))["success"]
    assert (await apply(data))["success"]
    assert len(api.uploads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "new_duplicate",
        "incomplete",
        "source_version",
        "source_parent",
        "digest",
        "expiry",
    ],
)
async def test_prewrite_rechecks_all_polygon_evidence(
    polygon_workflow, monkeypatch, change
):
    api, _ = polygon_workflow
    api.source = True
    data = (await preview(replace_node_id=900, expected_node_version=2))["data"]

    async def mutate():
        if change == "new_duplicate":
            api.map_extra = '<node id="999" version="1" lat="27.243239" lon="33.84426"><tag k="leisure" v="pitch"/></node>'
        elif change == "incomplete":
            api.map_error = "<osm><remark>truncated</remark></osm>"
        elif change == "source_version":
            api.source_version = 3
        elif change == "source_parent":
            api.parent_ways = True
        elif change == "digest":
            proposal = track_tools._PROPOSAL_STORE.get(data["proposal_id"])
            proposal.payload["create_nodes"][0]["lat"] = "27.2431000"
            with track_tools._PROPOSAL_STORE._connection() as c:
                c.execute(
                    "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
                    (json.dumps(proposal.payload), data["proposal_id"]),
                )
        elif change == "expiry":
            monkeypatch.setattr(
                track_tools.time, "time", lambda: data["expires_at_unix"] + 1
            )

    result = await apply(
        data, ConfirmationContext(data["proposal_digest"], callback=mutate)
    )
    assert not result["success"]
    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_options", [{"action": "decline"}, {"data": False}, {"digest": "0" * 64}]
)
async def test_polygon_never_writes_without_final_digest_confirmation(
    polygon_workflow, monkeypatch, context_options
):
    api, _ = polygon_workflow
    monkeypatch.setattr(config, "osm_require_host_confirmation", False)
    data = (await preview())["data"]
    result = await apply(
        data,
        ConfirmationContext(**{"digest": data["proposal_digest"], **context_options}),
    )
    assert not result["success"] and api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "way_tags",
        "closure",
        "order",
        "moved_corner",
        "tagged_vertex",
        "missing_corner",
        "way_version",
        "way_changeset",
    ],
)
async def test_wrong_area_readback_never_reports_success_or_reuploads(
    polygon_workflow, tamper
):
    api, store = polygon_workflow
    data = (await preview())["data"]
    api.tamper = tamper
    result = await apply(data)
    assert not result["success"]
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    assert store.get(data["proposal_id"]).status == "RECONCILE_REQUIRED"
    assert len(api.uploads) == 1
    assert not (await apply(data))["success"]
    assert len(api.uploads) == 1
    api.tamper = None
    assert (await edit_tools.verify_osm_edit(data["proposal_id"]))["success"]
    assert len(api.uploads) == 1


@pytest.mark.asyncio
async def test_timeout_recovers_exact_area_and_source_deletion_without_reupload(
    polygon_workflow,
):
    api, store = polygon_workflow
    api.source = True
    data = (await preview(replace_node_id=900, expected_node_version=2))["data"]
    api.upload_error = httpx.ReadTimeout("ambiguous upload")
    result = await apply(data)
    assert result["success"], result
    assert result["data"]["way_id"] == 301 and result["data"]["replaced_node_id"] == 900
    assert store.get(data["proposal_id"]).status == "APPLIED" and len(api.uploads) == 1


@pytest.mark.asyncio
async def test_empty_recovery_is_never_permission_to_retry(polygon_workflow):
    api, store = polygon_workflow
    data = (await preview())["data"]
    api.upload_error = httpx.ReadTimeout("unknown upload")
    api.apply_before_error = False
    api.download_override = "<osmChange/>"
    result = await apply(data)
    assert not result["success"] and result["proposal_status"] == "RECONCILE_REQUIRED"
    assert not (await edit_tools.verify_osm_edit(data["proposal_id"]))["success"]
    assert len(api.uploads) == 1


@pytest.mark.asyncio
async def test_source_deletion_cannot_be_silently_ignored(polygon_workflow):
    api, store = polygon_workflow
    api.source = True
    data = (await preview(replace_node_id=900, expected_node_version=2))["data"]
    api.skip_delete = True
    result = await apply(data)
    assert not result["success"]
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    assert not api.deleted
    assert not (await edit_tools.verify_osm_edit(data["proposal_id"]))["success"]
    assert len(api.uploads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["way_limit", "server_limit"])
async def test_server_limits_checked_before_polygon_search(polygon_workflow, limit):
    api, _ = polygon_workflow
    setattr(api, limit, 4)
    assert not (await preview())["success"]
    assert api.requests == []
