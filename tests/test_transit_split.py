"""Existing-way split previews, optimistic checks and exact receipt recovery."""

import copy
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager

import httpx
import pytest

from osm_edit_mcp import transit_split as split
from osm_edit_mcp.proposal_store import ProposalStore


class SplitAPI:
    def __init__(self):
        self.tags = {
            "highway": "primary",
            "name": "Тест",
            "oneway": "yes",
            "lanes:forward": "2",
        }
        self.way = {
            "id": 77,
            "version": 3,
            "nodes": [10, 20, 30, 40, 50],
            "tags": self.tags,
        }
        self.node_versions = {i: 1 for i in self.way["nodes"]}
        self.parent = None
        self.max_changes = 100
        self.readback = {}
        self.calls = []

    def transport(self, request):
        path = request.url.path.split("/0.6/")[-1]
        self.calls.append((request.method, path))
        assert request.method == "GET"
        root = ET.Element("osm")
        if path == "ways":
            element = ET.SubElement(
                root, "way", id="77", version=str(self.way["version"])
            )
            for ref in self.way["nodes"]:
                ET.SubElement(element, "nd", ref=str(ref))
            for k, v in self.tags.items():
                ET.SubElement(element, "tag", k=k, v=v)
        elif path == "nodes":
            for ref, version in self.node_versions.items():
                ET.SubElement(
                    root,
                    "node",
                    id=str(ref),
                    version=str(version),
                    lat="0",
                    lon=str(ref / 1000),
                )
        elif path == "way/77/relations":
            if self.parent:
                ET.SubElement(root, "relation", id=str(self.parent), version="1")
        elif path == "capabilities":
            ET.SubElement(
                ET.SubElement(root, "api"),
                "changesets",
                maximum_elements=str(self.max_changes),
            )
        elif path.startswith("way/"):
            root.append(self.readback[int(path.split("/")[-1])])
        else:
            raise AssertionError(path)
        return httpx.Response(200, content=ET.tostring(root))


@pytest.fixture
def network(monkeypatch, tmp_path):
    api = SplitAPI()

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(api.transport)
        ) as session:
            yield session

    async def identity(_):
        return {"user_id": 7}

    monkeypatch.setattr(split, "get_authenticated_client", client)
    monkeypatch.setattr(split, "verify_write_identity", identity)
    monkeypatch.setattr(
        split.track_tools,
        "_PROPOSAL_STORE",
        ProposalStore(str(tmp_path / "split.sqlite")),
    )
    monkeypatch.setattr(split.track_tools, "_PROPOSALS", {})
    return api, client


@pytest.mark.asyncio
async def test_split_preview_and_preflight(network):
    api, client = network
    result = await split.preview_bus_way_split(77, [40, 20], "проверено на месте")
    assert result["success"], result
    record = split.track_tools._PROPOSAL_STORE.get(result["data"]["proposal_id"])
    assert record.osm_uid == record.payload["split_osm_uid"] == 7
    payload = record.payload
    assert payload["changeset_source"] == "проверено на месте"
    assert payload["split_node_ids"] == [20, 40]
    assert payload["modify_ways"] == [
        {"id": 77, "version": 3, "tags": api.tags, "node_ids": [10, 20]}
    ]
    assert payload["create_ways"] == [
        {"id": -1, "tags": api.tags, "node_ids": [20, 30, 40]},
        {"id": -2, "tags": api.tags, "node_ids": [40, 50]},
    ]
    assert not (
        payload["delete_nodes"] or payload["modify_nodes"] or payload["create_nodes"]
    )
    xml = ET.fromstring(split.track_tools._build_osm_change(payload, 81))
    assert [n.tag for section in xml for n in section] == ["way"] * 3
    async with client() as c:
        await split.validate_split_context(c, payload)
        api.parent = 175
        with pytest.raises(ValueError, match="relations"):
            await split.validate_split_context(c, payload)
        api.parent = None
        api.node_versions[30] += 1
        with pytest.raises(ValueError, match="changed"):
            await split.validate_split_context(c, payload)
        api.node_versions[30] -= 1
        altered = copy.deepcopy(payload)
        altered["create_ways"][0]["node_ids"] = [20, 40]
        with pytest.raises(ValueError, match="changed"):
            await split.validate_split_context(c, altered)
        api.max_changes = 2
        with pytest.raises(ValueError, match="limit"):
            await split.validate_split_context(c, payload)


@pytest.mark.parametrize(
    "tag",
    ["junction", "change:lanes:forward", "turn:lanes", "destination:ref", "wikidata"],
)
@pytest.mark.asyncio
async def test_segment_tags_are_not_duplicated(network, tag):
    api, _ = network
    api.tags[tag] = "exists"
    response = await split.preview_bus_way_split(77, [30], "survey")
    assert not response["success"] and "Segment-specific" in str(response)


@pytest.mark.parametrize("cuts", [[10], [50], [999], [20, 20], []])
@pytest.mark.asyncio
async def test_only_interior_cuts(network, cuts):
    response = await split.preview_bus_way_split(77, cuts, "survey")
    assert not response["success"] and "interior" in str(response)


@pytest.mark.asyncio
async def test_recovery_and_exact_split_readback(network):
    api, client = network
    response = await split.preview_bus_way_split(77, [20, 40], "survey")
    payload = split.track_tools._PROPOSAL_STORE.get(
        response["data"]["proposal_id"]
    ).payload
    download = ET.fromstring(split.track_tools._build_osm_change(payload, 81))
    for element in download.iter("way"):
        old = int(element.attrib["id"])
        new = 77 if old > 0 else 200 - old
        element.attrib.update(id=str(new), version="4" if old > 0 else "1", uid="7")
        api.readback[new] = element
    rows = split.split_diff_from_download(ET.tostring(download), payload, 81)
    assert [r["new_id"] for r in rows] == [77, 201, 202]
    async with client() as c:
        assert (await split.verify_split_diff(c, payload, rows[::-1], 81))[
            "status"
        ] == "verified"
        assert (await split.verify_split_diff(c, payload, rows[:-1], 81))[
            "status"
        ] == "verification_incomplete"
        dup = [dict(r) for r in rows]
        dup[1]["new_id"] = 202
        assert (await split.verify_split_diff(c, payload, dup, 81))[
            "status"
        ] == "verification_incomplete"
        api.readback[201][0].attrib["ref"] = "99"
        assert (await split.verify_split_diff(c, payload, rows, 81))[
            "status"
        ] == "verification_incomplete"
    with pytest.raises(ValueError):
        split.split_diff_from_download(ET.tostring(download), payload, 81)
    api.readback[201][0].attrib["ref"] = "20"
    api.readback[77].attrib["uid"] = "66"
    with pytest.raises(ValueError, match="owner"):
        split.split_diff_from_download(ET.tostring(download), payload, 81)
    api.readback[77].attrib["uid"] = "7"
    ET.SubElement(download.find("create"), "node", id="2000")
    with pytest.raises(ValueError, match="Unexpected"):
        split.split_diff_from_download(ET.tostring(download), payload, 81)
