"""Offline publication tests for a reviewed, one-direction bus relation."""

import asyncio
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, track_tools, transit_apply
from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.proposal_store import ProposalStore, ProposalStoreError


class RouteOSM:
    def __init__(self):
        self.requests = []
        self.versions = {101: 1, 102: 4, 103: 1, 201: 2, 202: 1, 7: 3}
        self.parents = "<osm/>"
        self.created = None
        self.upload_problem = None
        self.close_status = 200
        self.changeset_open = False
        self.uid = 55
        self.next_relation = 33
        self.tags = {
            "type": "route",
            "route": "bus",
            "ref": "1",
            "from": "A",
            "to": "B",
            "public_transport:version": "2",
        }
        self.members = [
            {"type": "node", "ref": 201, "role": "platform", "version": 2},
            {"type": "node", "ref": 202, "role": "platform", "version": 1},
            {"type": "way", "ref": 7, "role": "", "version": 3},
        ]

    def proposal(self, store, proposal_id="p"):
        payload = {
            "action": "bus_route_create",
            "members": self.members,
            "relation_tags": self.tags,
            "blocking_issues": [],
            "changeset_comment": "Add surveyed route 1",
            "changeset_source": "survey",
            "summary": {"ref": "1", "from": "A", "to": "B"},
            "restriction_versions": {},
            "geometry_node_versions": {"101": 1, "102": 4, "103": 1},
        }
        return store.create(proposal_id, payload, config.current_api_base_url, 55, 600)

    def attach_client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.respond))

    def only_writes(self):
        return [req for req in self.requests if req.method != "GET"]

    def xml(self, kind, element):
        wrapper = ET.Element(kind)
        wrapper.append(element)
        return httpx.Response(200, content=ET.tostring(wrapper))

    async def respond(self, req):
        assert config.is_development_api
        await asyncio.sleep(0)
        self.requests.append(req)
        path = req.url.path
        if path.endswith("/ways"):
            assert req.url.params["ways"] == "7"
            way = ET.fromstring(
                '<way id="7"><nd ref="101"/><nd ref="102"/><nd ref="103"/></way>'
            )
            way.set("version", str(self.versions[7]))
            return self.xml("osm", way)
        if path.endswith("/nodes"):
            root = ET.Element("osm")
            for s in req.url.params["nodes"].split(","):
                ET.SubElement(
                    root,
                    "node",
                    id=s,
                    version=str(self.versions[int(s)]),
                    lat="38",
                    lon="68",
                )
            return httpx.Response(200, content=ET.tostring(root))
        if path.endswith("/relations"):
            return httpx.Response(200, text=self.parents)
        if req.method == "PUT" and path.endswith("/changeset/create"):
            return httpx.Response(200, text="77")
        if path.endswith("/77/upload"):
            if type(self.upload_problem) is int:
                return httpx.Response(self.upload_problem)
            root = ET.fromstring(req.content)
            assert root.tag == "osmChange" and [op.tag for op in root] == ["create"]
            assert len(root[0]) == 1 and root[0][0].tag == "relation"
            relation = root[0][0]
            assert relation.attrib == {"changeset": "77", "id": "-1"}
            relation.attrib.update(
                id=str(self.next_relation), version="1", uid=str(self.uid)
            )
            self.created = relation
            if self.upload_problem == "timeout":
                raise httpx.ReadTimeout("timeout")
            return httpx.Response(
                200,
                text='<diffResult><relation old_id="-1" new_id="33" new_version="1"/></diffResult>',
            )
        if path.endswith("/77/close"):
            return httpx.Response(self.close_status)
        if path.endswith("/77/download"):
            change = ET.Element("osmChange")
            if self.created is not None:
                ET.SubElement(change, "create").append(self.created)
            return httpx.Response(200, content=ET.tostring(change))
        if path.endswith("/changeset/77"):
            return self.xml(
                "osm",
                ET.Element(
                    "changeset",
                    id="77",
                    uid=str(self.uid),
                    open=str(self.changeset_open).lower(),
                    changes_count=str(int(self.created is not None)),
                ),
            )
        if path.endswith("/relation/33") and self.created is not None:
            return self.xml("osm", self.created)
        raise AssertionError(f"Unexpected request: {req.method} {path}")


@pytest.fixture()
def workflow(tmp_path, monkeypatch):
    api = RouteOSM()
    store = ProposalStore(tmp_path / "state" / "proposals.sqlite")
    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(transit_apply, "get_authenticated_client", api.attach_client)
    monkeypatch.setattr(transit_apply, "get_public_client", api.attach_client)

    async def identity(client):
        return {"user_id": api.uid, "permissions": ["write_api"]}

    monkeypatch.setattr(transit_apply, "verify_write_identity", identity)
    return api, store


class Confirmation:
    def __init__(self, digest, accept=True):
        self.digest = digest
        self.accept = accept
        self.calls = 0

    async def elicit(self, *args):
        self.calls += 1
        return SimpleNamespace(
            action="accept" if self.accept else "decline",
            data=SimpleNamespace(confirm=self.accept, proposal_digest=self.digest),
        )


async def apply(p, ctx=None, **kwargs):
    return await track_tools.apply_osm_edit(
        p.proposal_id, p.digest, ctx or Confirmation(p.digest), **kwargs
    )


@pytest.mark.asyncio
async def test_publish_exact_relation_verify_order_replay(workflow):
    api, store = workflow
    p = api.proposal(store)
    ctx = Confirmation(p.digest)
    result = await apply(p, ctx)
    assert result["success"], result
    receipt = result["data"]
    assert receipt["relation_id"] == 33 and receipt["changeset_closed"]
    assert [
        (el.attrib["type"], int(el.attrib["ref"]), el.attrib["role"])
        for el in api.created.findall("member")
    ] == [
        ("node", 201, "platform"),
        ("node", 202, "platform"),
        ("way", 7, ""),
    ]
    assert await apply(p, ctx) == {
        "success": True,
        "data": receipt,
        "message": "Transit proposal already applied",
    }
    assert ctx.calls == 1 and [r.method for r in api.only_writes()] == [
        "PUT",
        "POST",
        "PUT",
    ]
    assert (await edit_tools.verify_osm_edit(p.proposal_id))["success"]
    api.created.remove(api.created.findall("member")[0])
    assert not (await edit_tools.verify_osm_edit(p.proposal_id))["success"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "decline",
        "wrong digest",
        "foreign changeset",
        "wrong user",
        "stop changed",
        "way changed",
        "shape moved",
        "new restriction",
        "already mapped",
        "blocked",
    ],
)
async def test_reject_before_first_write(workflow, scenario):
    api, store = workflow
    p = api.proposal(store)
    if scenario == "stop changed":
        api.versions[201] += 1
    if scenario == "way changed":
        api.versions[7] += 1
    if scenario == "shape moved":
        api.versions[102] += 1
    if scenario == "new restriction":
        api.parents = '<osm><relation id="35" version="1"><tag k="type" v="restriction"/><tag k="restriction" v="no_left_turn"/></relation></osm>'
    if scenario == "already mapped":
        api.parents = '<osm><relation id="35" version="1"><tag k="type" v="route"/><tag k="route" v="bus"/><tag k="ref" v="1"/></relation></osm>'
    if scenario == "wrong user":
        api.uid = 10
    if scenario == "blocked":
        body = dict(p.payload, blocking_issues=["split way"])
        p = store.create("blocked", body, config.current_api_base_url, 55, 600)
    ctx = Confirmation(
        "wrong" if scenario == "wrong digest" else p.digest,
        accept=scenario != "decline",
    )
    result = await apply(
        p, ctx, changeset_id=98 if scenario == "foreign changeset" else None
    )
    assert not result["success"] and api.only_writes() == []


@pytest.mark.asyncio
async def test_uncertain_response_blocks_other_proposals_until_read_only_reconciliation(
    workflow,
):
    api, store = workflow
    p = api.proposal(store)
    other = api.proposal(store, "other")
    api.upload_problem = "timeout"
    result = await apply(p)
    assert result["status"] == "RECONCILE_REQUIRED" and api.created is not None
    assert not (await apply(other))["success"]
    assert not (await apply(p))["success"]
    assert len(api.only_writes()) == 3
    api.uid = 13
    assert not (await edit_tools.verify_osm_edit(p.proposal_id))["success"]
    api.uid = 55
    verified = await edit_tools.verify_osm_edit(p.proposal_id)
    assert verified["success"] and verified["data"]["relation_id"] == 33
    assert store.get(p.proposal_id).status == "APPLIED" and len(api.only_writes()) == 3


@pytest.mark.asyncio
async def test_parallel_reviewed_proposals_cannot_create_two_overlapping_relations(
    workflow,
):
    api, store = workflow
    a = api.proposal(store, "a")
    b = api.proposal(store, "b")
    outcomes = await asyncio.gather(apply(a), apply(b))
    assert sum(result["success"] for result in outcomes) == 1
    assert len([r for r in api.only_writes() if r.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_rejected_upload_and_failed_close_are_distinguished(workflow):
    api, store = workflow
    api.upload_problem = 409
    p = api.proposal(store)
    result = await apply(p)
    assert result["status"] == "FAILED" and result["data"]["changeset_closed"]
    api.upload_problem = None
    api.close_status = 500
    result = await apply(api.proposal(store, "second"))
    assert result["success"] and result["data"]["changeset_closed"] is False


def test_reverse_direction_does_not_block_forward_route(workflow):
    api, _ = workflow
    reverse = ET.fromstring(
        '<relation><tag k="type" v="route"/><tag k="route" v="bus"/><tag k="ref" v="1"/><tag k="from" v="B"/><tag k="to" v="A"/></relation>'
    )
    assert transit_apply.duplicate_route_ids({5: reverse}, api.tags, api.members) == []


@pytest.mark.parametrize(
    "legacy_name, matches",
    [
        ("Автобус №1", True),
        ("Автобуси 1: A – B", True),
        ("Троллейбус №1", False),
        ("Автобус №11", False),
    ],
)
def test_legacy_relation_with_number_only_in_name(workflow, legacy_name, matches):
    api, _ = workflow
    relation = ET.fromstring(
        '<relation><tag k="type" v="route"/><tag k="route" v="bus"/></relation>'
    )
    ET.SubElement(relation, "tag", k="name", v=legacy_name)
    assert (
        bool(transit_apply.duplicate_route_ids({5: relation}, api.tags, api.members))
        == matches
    )


@pytest.mark.asyncio
async def test_proven_closed_empty_changeset_releases_uncertain_reservation(workflow):
    api, store = workflow
    api.upload_problem = 503
    a = api.proposal(store)
    b = api.proposal(store, "after")
    assert (await apply(a))["status"] == "RECONCILE_REQUIRED"
    api.changeset_open = True
    assert not (await edit_tools.verify_osm_edit(a.proposal_id))["success"]
    assert (
        not (await apply(b))["success"]
        and store.get(a.proposal_id).status == "RECONCILE_REQUIRED"
    )
    api.changeset_open = False
    assert (await edit_tools.verify_osm_edit(a.proposal_id))["status"] == "FAILED"
    assert store.get(a.proposal_id).status == "FAILED"
    api.upload_problem = None
    assert (await apply(b))["success"]


def test_expired_claim_without_changeset_cannot_resume_after_a_fresh_claim(
    workflow, monkeypatch
):
    api, store = workflow
    old = api.proposal(store)
    store.claim(old.proposal_id, old.digest, old.api_target, old.osm_uid)
    monkeypatch.setattr(
        "src.osm_edit_mcp.proposal_store.time.time", lambda: old.expires_at + 2
    )
    fresh = api.proposal(store, "after")
    assert (
        store.claim(
            fresh.proposal_id, fresh.digest, fresh.api_target, fresh.osm_uid
        ).status
        == "APPLYING"
    )
    assert store.get(old.proposal_id).status == "FAILED"
    with pytest.raises(ProposalStoreError):
        store.bind_transit_changeset(old.proposal_id, 77)
