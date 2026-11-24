from types import SimpleNamespace

import pytest

from src.osm_edit_mcp.road_verification import verify_road_upload


def mapping(kind, old_id, new_id, new_version):
    return dict(type=kind, old_id=old_id, new_id=new_id, new_version=new_version)


class History:
    def __init__(self):
        self.objects = {
            "node/101/1": '<node id="101" version="1" changeset="9" visible="true" lat="41.1234568" lon="-0.0000001"/>',
            "way/101/1": '<way id="101" version="1" changeset="9" visible="true"><nd ref="12"/><nd ref="101"/><tag k="highway" v="track"/></way>',
            "way/20/4": '<way id="20" version="4" changeset="9" visible="true"><nd ref="101"/><nd ref="12"/><tag k="surface" v="gravel"/></way>',
            "node/30/8": '<node id="30" version="8" changeset="9" visible="false"/>',
        }
        self.reads = []

    async def get(self, url):
        path = url.split("/api/0.6/")[1]
        self.reads.append(path)
        value = self.objects.get(path, 404)
        if isinstance(value, int):
            return SimpleNamespace(status_code=value, text="")
        return SimpleNamespace(status_code=200, text=f"<osm>{value}</osm>")


@pytest.fixture
def upload():
    payload = {
        "action": "create",
        "create_nodes": [{"id": -1, "lat": 41.123456785, "lon": -0.00000005}],
        "create_ways": [{"id": -1, "node_ids": [12, -1], "tags": {"highway": "track"}}],
        "modify_ways": [
            {
                "id": 20,
                "version": 3,
                "node_ids": [-1, 12],
                "tags": {"surface": "gravel"},
            }
        ],
        "delete_nodes": [{"id": 30, "version": 7, "lat": 40, "lon": -8, "tags": {}}],
        "snapshot_ways": {"20": {"node_ids": [12, 30, 78], "version": 3}},
    }
    # Responses may be in a different order, and node/way ID spaces are independent.
    diff = [
        mapping("way", 20, 20, 4),
        mapping("way", -1, 101, 1),
        mapping("node", -1, 101, 1),
        mapping("node", 30, 30, 0),
    ]
    return History(), diff, payload


@pytest.mark.asyncio
async def test_full_road_diff_fetches_exact_versions_and_translates_refs(upload):
    history, diff, payload = upload
    result = await verify_road_upload(history, diff, payload, 9)
    assert result["status"] == "verified" and result["failures"] == []
    assert [row["outcome"] for row in result["verified"]] == [
        "modified",
        "created",
        "created",
        "deleted",
    ]
    assert history.reads == ["way/20/4", "way/101/1", "node/101/1", "node/30/8"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "element", "outcome"),
    [
        (7, 'visible="true" lat="40.0" lon="-8"', "skipped_visible"),
        (8, 'visible="false"', "skipped_already_deleted"),
        (10, 'visible="false"', "skipped_already_deleted"),
    ],
)
async def test_if_unused_distinguishes_skips_from_performed_deletion(
    upload, version, element, outcome
):
    history, diff, payload = upload
    diff[-1]["new_version"] = version
    history.objects[f"node/30/{version}"] = (
        f'<node id="30" version="{version}" changeset="42" {element}/>'
    )
    result = await verify_road_upload(history, diff, payload, 9)
    assert result["status"] == "verified"
    assert result["verified"][-1]["outcome"] == outcome


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.clear(),
        lambda d: d.pop(),
        lambda d: d.append(mapping("relation", -5, 123, 1)),
        lambda d: d.__setitem__(0, dict(d[1])),
        lambda d: d[1].update(new_id=20),  # created way aliases the modified way
        lambda d: d[2].update(new_id=12),  # created node aliases an untouched reference
        lambda d: d[2].update(new_id=78),  # aliases a node from the before snapshot
        lambda d: d[2].update(new_id=True),
        lambda d: d[2].update(new_version=True),
        lambda d: d[2].update(new_version=2),
        lambda d: d[0].update(type="relation"),
        lambda d: d[0].update(new_id=21),
        lambda d: d[0].update(new_version=5),
        lambda d: d[-1].update(new_version=6),
    ],
)
async def test_invalid_upload_mapping_fails_before_fetch(upload, mutation):
    history, diff, payload = upload
    mutation(diff)
    result = await verify_road_upload(history, diff, payload, 9)
    assert result["status"] == "verification_incomplete" and result["failures"]
    assert history.reads == []


@pytest.mark.asyncio
async def test_two_created_nodes_cannot_share_a_server_id(upload):
    history, diff, payload = upload
    payload["create_nodes"].append({"id": -2, "lat": 44, "lon": 40})
    diff.append(mapping("node", -2, 101, 1))
    result = await verify_road_upload(history, diff, payload, 9)
    assert result["status"] == "verification_incomplete"
    assert history.reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        ("way/20/4", 'ref="101"/><nd ref="12"', 'ref="12"/><nd ref="101"'),
        ("way/20/4", 'id="20"', 'id="21"'),
        ("way/20/4", 'version="4"', 'version="5"'),
        ("way/20/4", 'changeset="9"', 'changeset="10"'),
        ("way/20/4", 'k="surface"', 'k="highway"'),
        ("way/20/4", "</way>", '<tag k="surface" v="gravel"/></way>'),
        ("node/101/1", "41.1234568", "41.1234567"),
        ("node/101/1", "/>", '><tag k="amenity" v="cafe"/></node>'),
        ("node/101/1", 'visible="true"', 'visible="false"'),
        ("node/30/8", 'changeset="9"', 'changeset="10"'),
        ("node/30/8", 'visible="false"', 'visible="true"'),
    ],
)
async def test_historical_readback_must_match_complete_approved_operation(
    upload, path, before, after
):
    history, diff, payload = upload
    history.objects[path] = history.objects[path].replace(before, after)
    result = await verify_road_upload(history, diff, payload, 9)
    assert result["status"] == "verification_incomplete"
    assert result["failures"][0]["verification_error"]


@pytest.mark.asyncio
async def test_gone_or_current_tombstone_cannot_prove_our_conditional_delete(upload):
    history, diff, payload = upload
    history.objects["node/30/8"] = 410
    assert (await verify_road_upload(history, diff, payload, 9))[
        "status"
    ] == "verification_incomplete"
    diff[-1][
        "new_version"
    ] = 8  # skipped, but the claimed version was deleted by our changeset
    history.objects["node/30/8"] = (
        '<node id="30" version="8" changeset="9" visible="false"/>'
    )
    assert (await verify_road_upload(history, diff, payload, 9))[
        "status"
    ] == "verification_incomplete"
