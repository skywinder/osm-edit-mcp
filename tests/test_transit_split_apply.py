"""Exercise surveyed way splits through the public preview/apply/verify workflow."""

import asyncio
import xml.etree.ElementTree as ET
from copy import deepcopy

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, track_tools, transit_apply, transit_split
from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.proposal_store import ProposalStore
from tests.test_transit_apply import Confirmation


class SplitOSM:
    def __init__(self):
        road = ET.fromstring(
            '<way id="7" version="2"><nd ref="10"/><nd ref="20"/><nd ref="30"/>'
            '<nd ref="40"/><tag k="highway" v="tertiary"/><tag k="oneway" v="yes"/></way>'
        )
        self.ways = {7: road}
        self.uploads = []
        self.next_changeset = 70
        self.downloads = {}
        self.parent_xml = "<osm/>"
        self.outcome = "success"
        self.uid = 8
        self.hide_created = False

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.respond))

    async def respond(self, req):
        await asyncio.sleep(0)
        assert config.is_development_api and str(req.url).startswith(
            config.current_api_base_url + "/"
        )
        path = req.url.path
        root = ET.Element("osm")
        if path.endswith("/ways"):
            for ref in req.url.params["ways"].split(","):
                root.append(self.ways[int(ref)])
        elif path.endswith("/nodes"):
            for raw_id in req.url.params["nodes"].split(","):
                ET.SubElement(
                    root,
                    "node",
                    id=raw_id,
                    version="1",
                    lat="38.2",
                    lon=str(68.5 + int(raw_id) / 100000),
                )
        elif path.endswith("/relations"):
            return httpx.Response(200, text=self.parent_xml)
        elif path.endswith("/changeset/create"):
            self.next_changeset += 1
            return httpx.Response(200, text=str(self.next_changeset))
        elif path.endswith("/upload"):
            change = ET.fromstring(req.content)
            self.uploads.append(change)
            # OSM rejects the entire atomic diff on version conflict.
            modified = change.find("modify/way")
            assert modified is not None
            if (
                self.outcome == "409"
                or modified.attrib["version"] != self.ways[7].attrib["version"]
            ):
                return httpx.Response(409)
            assert [part.tag for part in change] == ["create", "modify"]
            diff = ET.Element("diffResult")
            committed = deepcopy(change)
            for section in committed:
                for way in section:
                    assert way.tag == "way"
                    old = int(way.attrib["id"])
                    new = old if old > 0 else 80 - old
                    version = int(way.get("version", "0")) + 1
                    way.attrib.update(
                        id=str(new), version=str(version), uid=str(self.uid)
                    )
                    self.ways[new] = way
                    ET.SubElement(
                        diff,
                        "way",
                        old_id=str(old),
                        new_id=str(new),
                        new_version=str(version),
                    )
            self.downloads[modified.attrib["changeset"]] = committed
            if self.outcome == "timeout":
                raise httpx.ReadTimeout("response lost")
            return httpx.Response(200, content=ET.tostring(diff))
        elif path.endswith("/close"):
            return httpx.Response(200)
        elif path.endswith("/download"):
            return httpx.Response(
                200, content=ET.tostring(self.downloads[path.split("/")[-2]])
            )
        elif "/way/" in path:
            ref = int(path.split("/")[-1])
            if self.hide_created and ref != 7:
                return httpx.Response(503)
            root.append(self.ways[ref])
        else:
            raise AssertionError(req.url)
        return httpx.Response(200, content=ET.tostring(root))


@pytest.fixture
def split_api(tmp_path, monkeypatch):
    api = SplitOSM()
    store = ProposalStore(tmp_path / "state" / "proposals.sqlite")
    for module in [track_tools, edit_tools]:
        monkeypatch.setattr(module, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: None)

    async def identity(client):
        return {"user_id": api.uid}

    async def limits(client):
        return 2000, 10000

    for module in [transit_apply, transit_split]:
        monkeypatch.setattr(module, "get_authenticated_client", api.client)
        monkeypatch.setattr(module, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    monkeypatch.setattr(transit_apply, "get_public_client", api.client)
    return api


async def preview():
    result = await transit_split.preview_bus_way_split(7, [20, 30], "survey")
    assert result["success"], result
    return result["data"]


async def apply(data, **kwargs):
    return await track_tools.apply_osm_edit(
        data["proposal_id"],
        data["proposal_digest"],
        Confirmation(data["proposal_digest"]),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_split_apply_verify_recovery_preserves_data_and_exact_order(split_api):
    api = split_api
    p = await preview()
    assert not (await apply(p, changeset_id=999))["success"]
    api.hide_created = True
    result = await apply(p)
    assert not result["success"] and result["status"] == "RECONCILE_REQUIRED"
    assert not (await apply(p))["success"] and len(api.uploads) == 1
    assert not (await edit_tools.verify_osm_edit(p["proposal_id"]))["success"]
    api.hide_created = False
    recovered = await edit_tools.verify_osm_edit(p["proposal_id"])
    assert recovered["success"] and recovered["data"]["way_ids"] == [7, 81, 82]
    assert (await apply(p))["success"] and len(api.uploads) == 1
    assert [[n.get("ref") for n in api.ways[i].findall("nd")] for i in (7, 81, 82)] == [
        ["10", "20"],
        ["20", "30"],
        ["30", "40"],
    ]
    for way in api.ways.values():
        assert {t.get("k"): t.get("v") for t in way.findall("tag")} == {
            "highway": "tertiary",
            "oneway": "yes",
        }
    api.ways[81].find("nd").set("ref", "12")
    assert not (await edit_tools.verify_osm_edit(p["proposal_id"]))["success"]


@pytest.mark.asyncio
async def test_concurrent_and_conflicting_splits_never_create_partial_ways(split_api):
    api = split_api
    p = await preview()
    api.outcome = "409"
    assert not (await apply(p))["success"]
    assert list(api.ways) == [7] and len(api.ways[7].findall("nd")) == 4
    api.outcome = "success"
    a, b = await preview(), await preview()
    results = await asyncio.gather(apply(a), apply(b))
    assert sum(r["success"] for r in results) == 1 and len(api.uploads) == 2
    assert set(api.ways) == {7, 81, 82}


@pytest.mark.asyncio
async def test_changed_parent_and_uncertain_split_upload(split_api):
    api = split_api
    p = await preview()
    api.parent_xml = '<osm><relation id="52" version="1"/></osm>'
    assert not (await apply(p))["success"] and not api.uploads
    api.parent_xml = "<osm/>"
    p = await preview()
    api.outcome = "timeout"
    assert (await apply(p))["status"] == "RECONCILE_REQUIRED"
    assert (await edit_tools.verify_osm_edit(p["proposal_id"]))["success"]
    assert len(api.uploads) == 1
