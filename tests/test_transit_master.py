"""Review, upload and reconcile a master containing versioned direction relations."""

import xml.etree.ElementTree as ET

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, track_tools, transit_apply, transit_master
from src.osm_edit_mcp.proposal_store import ProposalStore
from tests.test_transit_apply import Confirmation, RouteOSM


class MasterOSM(RouteOSM):
    def __init__(self):
        super().__init__()
        self.directions = {}
        for ref, origin, dest in [(21, "A", "B"), (22, "B", "A")]:
            rel = ET.Element("relation", id=str(ref), version="3")
            ET.SubElement(rel, "member", type="way", ref=str(ref + 100), role="")
            for k, v in {
                **self.tags,
                "from": origin,
                "to": dest,
                "network": "City",
            }.items():
                ET.SubElement(rel, "tag", k=k, v=v)
            self.directions[ref] = rel

    async def respond(self, req):
        if req.url.path.endswith("/relations") and "relations" in req.url.params:
            root = ET.Element("osm")
            root.extend(self.directions.values())
            return httpx.Response(200, content=ET.tostring(root))
        return await super().respond(req)


@pytest.fixture
def master_api(tmp_path, monkeypatch):
    api = MasterOSM()
    store = ProposalStore(tmp_path / "master" / "proposals.sqlite")
    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)

    async def identity(client):
        return {"user_id": api.uid, "permissions": ["write_api"]}

    for module in (transit_master, transit_apply):
        monkeypatch.setattr(module, "get_public_client", api.attach_client)
        monkeypatch.setattr(module, "get_authenticated_client", api.attach_client)
        monkeypatch.setattr(module, "verify_write_identity", identity)
    return api


async def preview(**kwargs):
    return await transit_master.preview_bus_route_master(
        [22, 21], "Field survey", source_basis="survey", prepare_upload=True, **kwargs
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_response", [False, True])
async def test_master_workflow(master_api, lost_response):
    result = await preview(name="Bus <1>")
    assert result["success"], result
    data = result["data"]
    assert data["relation_tags"]["network"] == "City"
    assert [row["tags"]["from"] for row in data["directions"]] == ["B", "A"]
    assert [m["ref"] for m in data["members"]] == [22, 21]
    page = track_tools.proposal_preview_resource(data["proposal_id"])
    assert "Bus &lt;1&gt;" in page and data["proposal_digest"] in page
    if lost_response:
        master_api.upload_problem = "timeout"
    result = await track_tools.apply_osm_edit(
        data["proposal_id"],
        data["proposal_digest"],
        Confirmation(data["proposal_digest"]),
    )
    if lost_response:
        assert result["status"] == "RECONCILE_REQUIRED"
    else:
        assert result["success"], result
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert verified["success"] and verified["data"]["relation_id"] == 33
    assert [r.method for r in master_api.only_writes()] == ["PUT", "POST", "PUT"]
    assert [
        (m.get("type"), m.get("ref"), m.get("role"))
        for m in master_api.created.findall("member")
    ] == [("relation", "22", ""), ("relation", "21", "")]
    assert master_api.created.find("tag[@k='route_master']").get("v") == "bus"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["parent", "version"])
async def test_changed_direction_blocks_first_write(master_api, change):
    data = (await preview())["data"]
    if change == "parent":
        master_api.parents = (
            '<osm><relation id="88"><tag k="type" v="route_master"/></relation></osm>'
        )
    else:
        master_api.directions[21].set("version", "4")
    result = await track_tools.apply_osm_edit(
        data["proposal_id"],
        data["proposal_digest"],
        Confirmation(data["proposal_digest"]),
    )
    assert not result["success"] and master_api.only_writes() == []
    if change == "parent":
        blocked = await preview()
        assert not blocked["success"] and blocked["data"]["existing_master_ids"] == [88]
        assert "proposal_id" not in blocked["data"]


@pytest.mark.asyncio
async def test_master_requires_same_ref_and_source(master_api):
    first = await transit_master.preview_bus_route_master(
        [21, 22], "Unknown", prepare_upload=True
    )
    assert not first["success"] and "proposal_id" not in first["data"]
    master_api.directions[22].find("tag[@k='ref']").set("v", "2")
    blocked = await preview()
    assert not blocked["success"] and "proposal_id" not in blocked["data"]
    assert master_api.only_writes() == []
