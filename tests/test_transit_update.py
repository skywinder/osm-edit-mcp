"""Review a live direction, update its existing ID and reconcile uncertain uploads."""

import xml.etree.ElementTree as ET
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, track_tools, transit_apply, transit_tools
from src.osm_edit_mcp.proposal_store import ProposalStore, ProposalStoreError
from tests.test_transit_apply import Confirmation
from tests.test_transit_tools import SurveyOSM


class UpdateOSM(SurveyOSM):
    def __init__(self):
        super().__init__()
        self.versions[203] = 5
        self.live = ET.Element("relation", id="33", version="8")
        for row in self.members:
            attributes = {k: str(row[k]) for k in ("type", "ref", "role")}
            if row["ref"] == 201:
                attributes["role"] = "platform_entry_only"
            ET.SubElement(self.live, "member", attributes)
        for key, value in {
            **self.tags,
            "name:tg": "Роҳ",
            "operator": "Old operator",
        }.items():
            ET.SubElement(self.live, "tag", k=key, v=value)
        self.history = None
        self.sibling = None

    def nodes_xml(self, ids):
        extra = {203: "68.001", 204: "68.00001"}
        root = super().nodes_xml([ref for ref in ids if ref not in extra])
        for ref in set(ids) & extra.keys():
            node = ET.SubElement(
                root, "node", id=str(ref), version="5", lat="37.99995", lon=extra[ref]
            )
            ET.SubElement(node, "tag", k="highway", v="bus_stop")
        return root

    async def respond(self, req):
        path = req.url.path
        if path.endswith("/relation/33"):
            return self.xml("osm", self.live)
        if path.endswith("/relation/33/9"):
            return self.xml("osm", self.history)
        if path.endswith("/relations"):
            root = ET.Element("osm")
            root.append(self.live)
            if self.sibling is not None:
                root.append(self.sibling)
            return httpx.Response(200, content=ET.tostring(root))
        if path.endswith("/77/upload"):
            self.requests.append(req)
            root = ET.fromstring(req.content)
            assert [op.tag for op in root] == ["modify"]
            assert [el.tag for el in root[0]] == ["relation"]
            relation = root[0][0]
            assert relation.attrib == {"id": "33", "version": "8", "changeset": "77"}
            relation.attrib.update(version="9", uid="55")
            self.live = relation
            self.history = deepcopy(relation)
            if self.upload_problem == "timeout":
                raise httpx.ReadTimeout("timeout")
            return httpx.Response(
                200,
                text='<diffResult><relation old_id="33" new_id="33" new_version="9"/></diffResult>',
            )
        if path.endswith("/77/download"):
            root = ET.Element("osmChange")
            ET.SubElement(root, "modify").append(self.history)
            return httpx.Response(200, content=ET.tostring(root))
        return await super().respond(req)


@pytest.fixture
def update(monkeypatch, tmp_path):
    api = UpdateOSM()
    store = ProposalStore(tmp_path / "proposals.sqlite")
    for module in (transit_tools, transit_apply):
        monkeypatch.setattr(module, "get_public_client", api.attach_client)
        monkeypatch.setattr(module, "get_authenticated_client", api.attach_client)
        monkeypatch.setattr(
            module, "verify_write_identity", AsyncMock(return_value={"user_id": 55})
        )
    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: {})
    return api, store


async def preview(**kwargs):
    args = dict(
        relation_id=33,
        source="Observed ride",
        source_basis="survey",
        prepare_upload=True,
    )
    return await transit_tools.preview_bus_route_update(**(args | kwargs))


async def approve(data):
    return await track_tools.apply_osm_edit(
        data["proposal_id"],
        data["proposal_digest"],
        Confirmation(data["proposal_digest"]),
    )


@pytest.mark.asyncio
async def test_update_preserves_identity_tags_roles_and_reports_exact_diff(update):
    api, _ = update
    api.sibling = deepcopy(api.live)
    api.sibling.set("id", "44")
    result = await preview(
        stop_ids=[201, 203, 202], tag_changes={"operator": None, "name": "A – B"}
    )
    assert result["success"], result
    data = result["data"]
    assert (
        data["relation_before"]["id"] == 33 and data["relation_before"]["version"] == 8
    )
    assert data["changes"] == {
        "tags": {
            "operator": {"before": "Old operator", "after": None},
            "name": {"before": None, "after": "A – B"},
        },
        "members": [
            {
                "operation": "insert",
                "before_range": [1, 1],
                "after_range": [1, 2],
                "before": [],
                "after": [{"type": "node", "ref": 203, "role": "platform"}],
            }
        ],
    }
    assert data["stops"][0]["role"] == "platform_entry_only"
    assert "before_range" in track_tools.proposal_preview_resource(data["proposal_id"])
    assert api.only_writes() == []
    receipt = (await approve(data))["data"]
    assert receipt["verification"] == {"status": "verified", "version": 9}
    assert receipt["relation_id"] == 33
    assert [x["ref"] for x in data["members"]] == [201, 203, 202, 7]
    assert transit_apply.element_tags(api.history) == data["relation_tags"]
    assert data["relation_tags"]["name:tg"] == "Роҳ"
    assert (await approve(data))["data"] == receipt
    assert [req.method for req in api.only_writes()] == ["PUT", "POST", "PUT"]
    api.history[0].set("role", "platform")
    assert not (await edit_tools.verify_osm_edit(data["proposal_id"]))["success"]


@pytest.mark.asyncio
async def test_noop_source_and_unsupported_existing_members_do_not_prepare_writes(
    update,
):
    api, store = update
    noop = await preview()
    assert not noop["success"] and noop["data"]["changes"] == {
        "members": [],
        "tags": {},
    }
    assert not (await preview(source_basis="unconfirmed", tag_changes={"from": "A2"}))[
        "success"
    ]
    assert not (await preview(tag_changes={"ref": None}))["success"]
    api.live[0].set("type", "way")
    assert not (await preview(stop_ids=[201, 202]))["success"]
    assert not store.list() and not api.only_writes()


@pytest.mark.asyncio
async def test_stale_baseline_rejected_before_any_write(update):
    api, _ = update
    data = (await preview(tag_changes={"operator": "New"}))["data"]
    api.live.set("version", "9")
    result = await approve(data)
    assert result["status"] == "FAILED" and not api.only_writes()


@pytest.mark.asyncio
async def test_recovery_checks_original_version_after_later_edit_and_never_reposts(
    update,
):
    api, store = update
    data = (await preview(stop_ids=[201, 203, 202]))["data"]
    api.upload_problem = "timeout"
    assert (await approve(data))["status"] == "RECONCILE_REQUIRED"
    assert not (await approve(data))["success"]
    api.live.set("version", "10")
    api.live[0].set("role", "platform")
    recovered = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert recovered["success"] and recovered["data"]["verification"]["version"] == 9
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert len([req for req in api.only_writes() if req.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_competing_relation_claims_with_different_refs_and_members_are_blocked(
    update,
):
    _, store = update
    first = (await preview(tag_changes={"ref": "2"}))["data"]
    original = store.get(first["proposal_id"])
    store.claim(
        original.proposal_id, original.digest, original.api_target, original.osm_uid
    )
    second = deepcopy(original.payload)
    second["relation_before"]["tags"]["ref"] = "8"
    second["relation_tags"]["ref"] = "9"
    second["relation_before"]["members"] = second["members"] = [
        {"type": "way", "ref": 999, "role": ""}
    ]
    p = store.create("different", second, original.api_target, original.osm_uid, 600)
    with pytest.raises(ProposalStoreError, match="Overlapping"):
        store.claim(p.proposal_id, p.digest, p.api_target, p.osm_uid)


@pytest.mark.asyncio
async def test_block_new_exact_duplicate_direction(update):
    api, store = update
    api.sibling = deepcopy(api.live)
    api.sibling.set("id", "44")
    api.sibling.insert(1, ET.Element("member", type="node", role="platform", ref="203"))
    result = await preview(stop_ids=[201, 203, 202])
    assert result["data"]["duplicate_relation_ids"] == [44]
    assert not result["success"] and not store.list()


@pytest.mark.asyncio
async def test_update_preview_via_mcp_preserves_omitted_fields(update):
    from mcp.shared.memory import create_connected_server_and_client_session

    from src.osm_edit_mcp.server import mcp

    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "preview_bus_route_update",
            {
                "relation_id": 33,
                "source": "Observed trip",
                "source_basis": "survey",
                "tag_changes": {"operator": None},
            },
        )
    assert result.structuredContent["success"]
    data = result.structuredContent["data"]
    assert "proposal_id" not in data and not data["changes"]["members"]
    assert data["changes"]["tags"] == {
        "operator": {"before": "Old operator", "after": None}
    }


def test_repeated_restricted_visits_preserve_exact_sequence_or_require_review():
    from src.osm_edit_mcp.transit_update import preserve_boarding_roles

    old = [
        {"type": "node", "ref": 1, "role": "platform_entry_only"},
        {"type": "node", "ref": 1, "role": "platform_exit_only"},
    ]
    selected = [{"type": "node", "ref": 1, "role": "platform"} for _ in range(2)]
    with pytest.raises(ValueError, match="visit count"):
        preserve_boarding_roles(old, selected[:1])
    preserve_boarding_roles(old, selected)
    assert selected == old


@pytest.mark.asyncio
async def test_relocated_restricted_terminal_requires_reviewed_role(update):
    _, store = update
    blocked = await preview(stop_ids=[204, 202])
    assert not blocked["success"] and "boarding_roles" in blocked["detail"]
    assert not store.list()
    mismatched = await preview(
        stop_ids=[204, 202], boarding_roles=["stop_entry_only", None]
    )
    assert not mismatched["success"] and not store.list()
    reviewed = await preview(
        stop_ids=[204, 202], boarding_roles=["platform_entry_only", None]
    )
    assert reviewed["success"], reviewed
    assert reviewed["data"]["changes"]["members"][0]["after"] == [
        {"type": "node", "role": "platform_entry_only", "ref": 204}
    ]


@pytest.mark.asyncio
async def test_existing_direction_without_endpoint_tags_keeps_unsupplied_tags_absent(
    update,
):
    api, _ = update
    for tag in list(api.live.iterfind("tag")):
        if tag.get("k") in {"ref", "from", "to"}:
            api.live.remove(tag)
    result = await preview(tag_changes={"operator": "City"})
    assert result["success"], result
    data = result["data"]
    assert not ({"ref", "from", "to"} & data["relation_tags"].keys())
    assert "relation/33" in track_tools.proposal_preview_resource(data["proposal_id"])
    assert (await approve(data))["success"]
