"""Offline-only tests for reviewed single-node tag proposals."""

import xml.etree.ElementTree as ET

import httpx
import pytest

from src.osm_edit_mcp import track_tools
from src.osm_edit_mcp.proposal_store import ProposalStore


@pytest.fixture
def node_client(monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET", "Preview must never write OSM"
        assert request.url.path.endswith("/node/42")
        return httpx.Response(
            200,
            text='<osm><node id="42" version="3" lat="40.1234567" lon="44.7654321"><tag k="amenity" v="restaurant"/><tag k="name" v="Example"/><tag k="addr:city" v="Yerevan"/></node></osm>',
        )

    async def identity(client):
        return {"user_id": 123, "username": "test-mapper", "permissions": ["write_api"]}

    async def limits(client):
        return 2000, 10000

    monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    monkeypatch.setattr(
        track_tools,
        "get_authenticated_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(track_tools, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "get_current_user_info", lambda: None)
    monkeypatch.setattr(
        track_tools, "_PROPOSAL_STORE", ProposalStore(tmp_path / "proposals.sqlite")
    )
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    return calls


async def preview(**overrides):
    args = dict(
        node_id=42,
        expected_version=3,
        tag_changes={"amenity": None, "disused:amenity": "restaurant"},
        changeset_comment="Record confirmed permanent closure",
        changeset_source="local knowledge",
    )
    args.update(overrides)
    return await track_tools.preview_node_tag_edit(**args)


@pytest.mark.asyncio
async def test_preview_is_durable_identity_bound_exact_tag_only_diff(node_client):
    result = await preview()
    assert result["success"], result
    data = result["data"]
    assert data["osm_uid"] == 123
    assert data["confirmation_required"] is True
    node = data["operations"]["modify_nodes"][0]
    assert node == {
        "id": 42,
        "version": 3,
        "lat": "40.1234567",
        "lon": "44.7654321",
        "tags": {
            "disused:amenity": "restaurant",
            "name": "Example",
            "addr:city": "Yerevan",
        },
    }
    assert data["operations"]["delete_nodes"] == []
    assert (
        data["current_geojson"]["features"][0]["geometry"]
        == data["proposed_geojson"]["features"][0]["geometry"]
    )
    track_tools._PROPOSALS.clear()
    stored = track_tools._get_proposal(data["proposal_id"])
    assert stored.digest == data["proposal_digest"]
    assert stored.payload["snapshot_nodes"]["42"]["tags"]["amenity"] == "restaurant"
    assert len(node_client) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"node_id": 0},
        {"node_id": True},
        {"node_id": "42"},
        {"expected_version": 0},
        {"expected_version": 2},
        {"expected_version": True},
        {"tag_changes": {}},
        {"tag_changes": {"k" + str(i): "v" for i in range(21)}},
        {"tag_changes": {"": "v"}},
        {"tag_changes": {"x": ""}},
        {"tag_changes": {"x": "é" * 128}},
        {"tag_changes": {"x\u0001": "v"}},
        {"tag_changes": {"x": "v\u0000"}},
        {"tag_changes": {"x": 2}},
        {"tag_changes": {"absent": None}},
        {"tag_changes": {"amenity": "restaurant"}},
        {"changeset_comment": " "},
        {"changeset_source": ""},
        {"changeset_comment": "x" * 256},
        {"changeset_source": "Google Maps"},
    ],
)
async def test_rejects_invalid_or_stale_patch_without_storing(node_client, overrides):
    result = await preview(**overrides)
    assert result["success"] is False, result
    assert not track_tools._PROPOSALS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attributes",
    [
        'id="43" version="3" lat="40" lon="44"',
        'id="42" version="3" lat="nan" lon="44"',
        'id="42" version="3" lat="91" lon="44"',
        'id="42" version="3" lat="40" lon="181"',
        'id="42" version="3" lat="40" lon="44" visible="false"',
    ],
)
async def test_rejects_wrong_or_unusable_live_node(
    node_client, monkeypatch, attributes
):
    def handler(request):
        return httpx.Response(
            200,
            text=f'<osm><node {attributes}><tag k="amenity" v="restaurant"/></node></osm>',
        )

    monkeypatch.setattr(
        track_tools,
        "get_authenticated_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await preview()
    assert result["success"] is False
    assert not track_tools._PROPOSALS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        ('id="42"', 'id="43"'),
        ('version="3"', 'version="4"'),
        ('lat="40.1234567"', 'lat="40.2"'),
        ('v="restaurant"', 'v="cafe"'),
    ],
)
async def test_preapply_rechecks_full_node_snapshot(node_client, mutation):
    result = await preview()
    payload = track_tools._get_proposal(result["data"]["proposal_id"]).payload
    xml = node_client[0]  # The transport has not performed any public request.
    async with track_tools.get_authenticated_client() as client:
        response = await client.get(str(xml.url))
    changed = response.text.replace(*mutation)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=changed))
    ) as client:
        with pytest.raises(ValueError, match="changed"):
            await track_tools._validate_proposal_versions(client, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["geometry", "version", "id", "extra_node", "create", "no_snapshot"]
)
async def test_preapply_rejects_non_tag_only_operations(node_client, mutation):
    data = (await preview())["data"]
    payload = track_tools._get_proposal(data["proposal_id"]).payload
    node = payload["modify_nodes"][0]
    if mutation == "geometry":
        node["lat"] = "40.2"
    elif mutation == "version":
        node["version"] = 2
    elif mutation == "id":
        node["id"] = 43
    elif mutation == "extra_node":
        payload["modify_nodes"].append(dict(node))
    elif mutation == "create":
        payload["create_nodes"] = [dict(node)]
    else:
        payload["snapshot_nodes"] = {}
    async with track_tools.get_authenticated_client() as client:
        with pytest.raises(ValueError, match="tag-only"):
            await track_tools._validate_proposal_versions(client, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_response", ["empty_diff", "wrong_diff", "wrong_tags", "wrong_coords"]
)
async def test_modified_node_verification_checks_exact_result(
    node_client, bad_response
):
    data = (await preview())["data"]
    node = data["operations"]["modify_nodes"][0]
    diff = [{"type": "node", "old_id": 42, "new_id": 42, "new_version": 4}]
    if bad_response == "empty_diff":
        diff = []
    elif bad_response == "wrong_diff":
        diff[0]["new_id"] = 43
    lat = "40.2" if bad_response == "wrong_coords" else node["lat"]
    tags = node["tags"] if bad_response != "wrong_tags" else {"amenity": "restaurant"}
    xml_node = ET.Element(
        "node", {"id": "42", "version": "4", "lat": lat, "lon": node["lon"]}
    )
    for key, value in tags.items():
        ET.SubElement(xml_node, "tag", {"k": key, "v": value})
    xml = "<osm>" + ET.tostring(xml_node, encoding="unicode") + "</osm>"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=xml))
    ) as client:
        result = await track_tools._verify_diff_results(
            client, diff, expected_nodes=[node]
        )
    assert result["status"] == "verification_incomplete"


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_tags", [False, True])
async def test_normal_apply_verifies_node_and_never_retries_upload(
    node_client, monkeypatch, wrong_tags
):
    data = (await preview())["data"]
    calls = []
    uploaded = False

    def handler(request):
        nonlocal uploaded
        calls.append(request)
        assert "dev.openstreetmap.org" in str(request.url)
        if request.method == "POST":
            uploaded = True
            return httpx.Response(
                200,
                text='<diffResult><node old_id="42" new_id="42" new_version="4"/></diffResult>',
            )
        if request.method == "PUT":
            return httpx.Response(200, text="123")
        if request.url.path.endswith("/download"):
            return httpx.Response(200, text="<osmChange/>")
        tags = dict(data["operations"]["modify_nodes"][0]["tags"])
        if not uploaded or wrong_tags:
            tags.pop("disused:amenity")
            tags["amenity"] = "restaurant"
        root = ET.Element("osm")
        node = ET.SubElement(
            root,
            "node",
            {
                "id": "42",
                "version": "4" if uploaded else "3",
                "lat": "40.1234567",
                "lon": "44.7654321",
            },
        )
        for key, value in tags.items():
            ET.SubElement(node, "tag", {"k": key, "v": value})
        return httpx.Response(200, text=ET.tostring(root, encoding="unicode"))

    monkeypatch.setattr(
        track_tools,
        "get_authenticated_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(
        track_tools, "load_oauth_token", lambda: {"access_token": "offline-test"}
    )
    monkeypatch.setattr(track_tools.config, "osm_require_host_confirmation", False)
    result = await track_tools.apply_osm_edit(
        data["proposal_id"], data["proposal_digest"], None
    )
    assert result["success"] is (not wrong_tags), result
    if wrong_tags:
        assert result["proposal_status"] == "RECONCILE_REQUIRED"
    else:
        assert result["data"]["verification"]["status"] == "verified"
    await track_tools.apply_osm_edit(data["proposal_id"], data["proposal_digest"], None)
    assert len([call for call in calls if call.method == "POST"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["preview", "apply"])
@pytest.mark.parametrize("limit_source", ["local", "server"])
async def test_node_operation_respects_element_limits(
    node_client, monkeypatch, stage, limit_source
):
    data = (await preview())["data"] if stage == "apply" else None
    if limit_source == "local":
        monkeypatch.setattr(track_tools.config, "max_changeset_size", 0)
    else:

        async def limits(client):
            return 2000, 0

        monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    if stage == "preview":
        assert (await preview())["success"] is False
    else:
        payload = track_tools._get_proposal(data["proposal_id"]).payload
        async with track_tools.get_authenticated_client() as client:
            with pytest.raises(ValueError, match="limit"):
                await track_tools._validate_proposal_versions(client, payload)


@pytest.mark.asyncio
async def test_audit_verifies_approved_node_tags(node_client, monkeypatch):
    from src.osm_edit_mcp import edit_tools

    data = (await preview())["data"]
    track_tools._PROPOSAL_STORE.claim(
        data["proposal_id"],
        data["proposal_digest"],
        data["api_target"],
        data["osm_uid"],
    )
    track_tools._PROPOSAL_STORE.finish(
        data["proposal_id"],
        "APPLIED",
        receipt={
            "diff_results": [
                {"type": "node", "old_id": 42, "new_id": 42, "new_version": 3}
            ],
        },
    )
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", track_tools._PROPOSAL_STORE)
    monkeypatch.setattr(
        edit_tools, "get_public_client", track_tools.get_authenticated_client
    )
    result = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert result["success"] is False


@pytest.mark.asyncio
async def test_node_preview_is_discoverable_in_safe_capabilities(
    node_client, monkeypatch
):
    from src.osm_edit_mcp import edit_tools, server

    assert server.preview_node_tag_edit is track_tools.preview_node_tag_edit
    monkeypatch.setattr(
        edit_tools, "get_authenticated_client", track_tools.get_authenticated_client
    )
    monkeypatch.setattr(
        edit_tools, "verify_write_identity", track_tools.verify_write_identity
    )

    async def unavailable():
        return {"available": False}

    monkeypatch.setattr(edit_tools, "valhalla_status", unavailable)
    result = await edit_tools.get_edit_capabilities()
    assert "preview_node_tag_edit" in result["data"]["safe_write_tools"]
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    assert "update_osm_node" not in tools
    assert tools["preview_node_tag_edit"].annotations.readOnlyHint is True


@pytest.mark.asyncio
@pytest.mark.parametrize("host_action", ["unavailable", "decline", "wrong_digest"])
async def test_production_host_confirmation_cannot_be_skipped(
    node_client, monkeypatch, host_action
):
    from types import SimpleNamespace

    data = (await preview())["data"]

    async def elicit(message, schema):
        assert data["proposal_digest"] in message
        if host_action == "unavailable":
            raise RuntimeError("No host elicitation")
        # Never simulate a production acceptance: wrong digest is a declined form.
        return SimpleNamespace(
            action="decline",
            data=track_tools.ApplyConfirmation(
                confirm=True,
                proposal_digest=(
                    "wrong"
                    if host_action == "wrong_digest"
                    else data["proposal_digest"]
                ),
            ),
        )

    monkeypatch.setattr(track_tools.config, "osm_use_dev_api", False)
    monkeypatch.setattr(track_tools.config, "osm_require_host_confirmation", False)
    result = await track_tools.apply_osm_edit(
        data["proposal_id"], data["proposal_digest"], SimpleNamespace(elicit=elicit)
    )
    assert result["success"] is False
    assert len(node_client) == 1


@pytest.mark.asyncio
async def test_preview_requires_verified_write_identity(node_client, monkeypatch):
    async def denied(client):
        raise PermissionError("write_api missing")

    monkeypatch.setattr(track_tools, "verify_write_identity", denied)
    result = await preview()
    assert result["success"] is False
    assert not track_tools._PROPOSALS
    assert not node_client


@pytest.mark.parametrize("bad_id", [True, "42", 42.0])
def test_mcp_node_id_does_not_coerce_nonintegers(bad_id):
    from pydantic import ValidationError

    tool = track_tools.mcp._tool_manager.get_tool("preview_node_tag_edit")
    with pytest.raises(ValidationError):
        tool.fn_metadata.arg_model.model_validate(
            {
                "node_id": bad_id,
                "expected_version": 3,
                "tag_changes": {"amenity": None},
                "changeset_comment": "Closure",
                "changeset_source": "user report",
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["digest", "account", "target", "expired", "missing"]
)
async def test_node_apply_retains_existing_identity_digest_and_expiry_gates(
    node_client, monkeypatch, failure
):
    data = (await preview())["data"]
    monkeypatch.setattr(
        track_tools, "load_oauth_token", lambda: {"access_token": "offline-test"}
    )
    digest = data["proposal_digest"]
    if failure == "digest":
        digest = "wrong"
    elif failure == "account":

        async def different_identity(client):
            return {"user_id": 124}

        monkeypatch.setattr(track_tools, "verify_write_identity", different_identity)
    elif failure == "target":
        monkeypatch.setattr(track_tools.config, "osm_use_dev_api", False)
    elif failure == "expired":
        track_tools._get_proposal(data["proposal_id"]).expires_at = 1
    else:

        def handler(request):
            assert request.method == "GET"
            return httpx.Response(404, text="not found")

        monkeypatch.setattr(
            track_tools,
            "get_authenticated_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
    # Offline unit test of the existing reservation gate, not a production host.
    result = await track_tools._apply_osm_edit_internal(data["proposal_id"], digest)
    assert result["success"] is False
    assert len(node_client) == 1


def test_osm_change_serializes_existing_node_tag_update():
    payload = {
        "create_nodes": [],
        "create_ways": [],
        "modify_ways": [],
        "delete_nodes": [],
        "modify_nodes": [
            {
                "id": 42,
                "version": 3,
                "lat": "40.1234567",
                "lon": "44.7654321",
                "tags": {"disused:amenity": "restaurant"},
            }
        ],
    }
    root = ET.fromstring(track_tools._build_osm_change(payload, 123))
    node = root.find("modify/node")
    assert node is not None
    assert node.attrib == {
        "id": "42",
        "version": "3",
        "lat": "40.1234567",
        "lon": "44.7654321",
        "changeset": "123",
    }
    assert node.find("tag").attrib == {"k": "disused:amenity", "v": "restaurant"}
    assert root.find("create") is None
    assert root.find("delete") is None
