"""Exercise the real reviewed creation workflow against offline HTTP transports."""

import asyncio
import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import httpx
import pytest

from src.osm_edit_mcp import edit_tools, node_tools, track_tools, write_tools
from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.proposal_store import ProposalStore


def created_node_xml(**overrides):
    attributes = {
        "id": "201",
        "version": "1",
        "changeset": "77",
        "visible": "true",
        "lat": "27.3329940",
        "lon": "33.6937310",
    }
    tags = overrides.pop("tags", {"shop": "supermarket"})
    attributes.update(overrides)
    element = ET.Element("node", attributes)
    for key, value in tags.items():
        ET.SubElement(element, "tag", {"k": key, "v": value})
    return ET.tostring(element, encoding="unicode")


class OfflineOSM:
    def __init__(self):
        self.requests = []
        self.map_xml = '<osm version="0.6"/>'
        self.node_xml = created_node_xml()
        self.download = f"<osmChange><create>{created_node_xml()}</create></osmChange>"
        self.upload_exception = None
        self.upload_response = (
            '<diffResult><node old_id="-1" new_id="201" '
            'new_version="1"/></diffResult>'
        )
        self.uid = 123

    @property
    def uploads(self):
        return [request for request in self.requests if request.method == "POST"]

    @property
    def changeset_creates(self):
        return [
            request
            for request in self.requests
            if request.method == "PUT"
            and request.url.path.endswith("/changeset/create")
        ]

    @property
    def writes(self):
        return [request for request in self.requests if request.method != "GET"]

    async def handle(self, request):
        assert config.is_development_api, "Tests must never use production"
        assert str(request.url).startswith(config.current_api_base_url + "/")
        self.requests.append(request)
        await asyncio.sleep(0)
        path = request.url.path
        if request.method == "GET" and path.endswith("/map"):
            return httpx.Response(200, text=self.map_xml)
        if request.method == "PUT" and path.endswith("/changeset/create"):
            return httpx.Response(200, text="77")
        if request.method == "POST" and path.endswith("/changeset/77/upload"):
            if self.upload_exception is not None:
                raise self.upload_exception
            return httpx.Response(200, text=self.upload_response)
        if request.method == "GET" and path.endswith("/node/201"):
            return httpx.Response(200, text=f"<osm>{self.node_xml}</osm>")
        if request.method == "GET" and path.endswith("/changeset/77/download"):
            if isinstance(self.download, Exception):
                raise self.download
            if isinstance(self.download, int):
                return httpx.Response(self.download)
            return httpx.Response(200, text=self.download)
        if request.method == "PUT" and path.endswith("/changeset/77/close"):
            return httpx.Response(200)
        raise AssertionError(f"Unexpected offline request: {request.method} {path}")


@pytest.fixture
def workflow(monkeypatch, tmp_path):
    api = OfflineOSM()
    store = ProposalStore(tmp_path / "proposals.sqlite")

    def client():
        return httpx.AsyncClient(transport=httpx.MockTransport(api.handle))

    async def identity(client):
        return {
            "user_id": api.uid,
            "username": "offline-test-mapper",
            "permissions": ["write_api"],
        }

    async def limits(client):
        return 2000, 10000

    monkeypatch.setattr(track_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(edit_tools, "_PROPOSAL_STORE", store)
    monkeypatch.setattr(track_tools, "_PROPOSALS", {})
    monkeypatch.setattr(track_tools, "verify_write_identity", identity)
    monkeypatch.setattr(track_tools, "_fetch_api_limits", limits)
    monkeypatch.setattr(track_tools, "get_authenticated_client", client)
    monkeypatch.setattr(edit_tools, "get_public_client", client)
    monkeypatch.setattr(write_tools, "get_authenticated_client", client)
    monkeypatch.setattr(
        track_tools, "load_oauth_token", lambda: {"access_token": "offline-test"}
    )
    monkeypatch.setattr(
        write_tools, "load_oauth_token", lambda: {"access_token": "offline-test"}
    )
    monkeypatch.setattr(config, "osm_require_host_confirmation", True)
    return api, store


async def preview():
    result = await node_tools.preview_node_create(
        latitude=27.332994,
        longitude=33.693731,
        tags={"shop": "supermarket"},
        changeset_comment="Add supermarket observed on site",
        changeset_source="survey",
    )
    assert result["success"], result
    return result["data"]


class ConfirmationContext:
    def __init__(
        self, digest, *, action="accept", confirm=True, data=True, callback=None
    ):
        self.digest = digest
        self.action = action
        self.confirm = confirm
        self.data = data
        self.callback = callback
        self.messages = []

    async def elicit(self, message, schema):
        self.messages.append(message)
        assert schema is track_tools.ApplyConfirmation
        if self.callback is not None:
            await self.callback()
        return SimpleNamespace(
            action=self.action,
            data=(
                track_tools.ApplyConfirmation(
                    confirm=self.confirm, proposal_digest=self.digest
                )
                if self.data
                else None
            ),
        )


async def apply(data, context=None, **kwargs):
    if context is None:
        context = ConfirmationContext(data["proposal_digest"])
    return await track_tools.apply_osm_edit(
        proposal_id=data["proposal_id"],
        proposal_digest=data["proposal_digest"],
        context=context,
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_options",
    [
        {"action": "decline"},
        {"action": "cancel"},
        {"confirm": False},
        {"data": False},
        {"digest": "0" * 64},
    ],
)
async def test_decline_cancel_missing_data_or_wrong_confirmation_digest_never_write(
    workflow, context_options
):
    api, store = workflow
    data = await preview()
    options = {"digest": data["proposal_digest"], **context_options}
    context = ConfirmationContext(**options)
    result = await apply(data, context)

    assert result["success"] is False
    assert result["error"] == "Confirmation declined"
    assert len(context.messages) == 1
    assert api.writes == []
    assert store.get(data["proposal_id"]).status == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_client_without_elicitation_cannot_create_changeset_or_node(workflow):
    api, _ = workflow
    data = await preview()
    result = await apply(data, object())

    assert result["success"] is False
    assert result["error"] == "Host confirmation unavailable"
    assert api.writes == []


@pytest.mark.asyncio
async def test_wrong_apply_digest_is_rejected_before_requesting_confirmation(workflow):
    api, _ = workflow
    data = await preview()
    context = ConfirmationContext(data["proposal_digest"])
    result = await apply({**data, "proposal_digest": "0" * 64}, context)

    assert result["success"] is False
    assert result["error"] == "Proposal digest mismatch"
    assert context.messages == []
    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("during_confirmation", [False, True])
async def test_expired_ttl_prevents_writes_before_or_after_confirmation(
    workflow, during_confirmation
):
    api, store = workflow
    data = await preview()

    async def expire():
        with store._connection() as connection:
            connection.execute(
                "UPDATE proposals SET expires_at=0 WHERE proposal_id=?",
                (data["proposal_id"],),
            )
        if not during_confirmation:
            track_tools._PROPOSALS.clear()

    context = ConfirmationContext(
        data["proposal_digest"], callback=expire if during_confirmation else None
    )
    if not during_confirmation:
        await expire()
    result = await apply(data, context)

    assert result["success"] is False
    assert api.writes == []
    assert len(context.messages) == int(during_confirmation)
    assert store.get(data["proposal_id"], include_expired=True).status == "EXPIRED"


@pytest.mark.asyncio
async def test_full_apply_and_verification_persist_exact_real_ids_and_operations(
    workflow,
):
    api, store = workflow
    data = await preview()
    assert api.writes == []
    context = ConfirmationContext(data["proposal_digest"])
    result = await apply(data, context)

    assert result["success"], result
    assert result["data"]["node_id"] == 201
    assert result["data"]["changeset_id"] == 77
    assert result["data"]["verification"]["status"] == "verified"
    assert result["data"]["changeset_closed"] is True
    assert data["proposal_digest"] in context.messages[0]
    assert len(api.changeset_creates) == len(api.uploads) == 1
    changeset = ET.fromstring(api.changeset_creates[0].content).find("changeset")
    assert {child.get("k"): child.get("v") for child in changeset}["source"] == "survey"
    upload = ET.fromstring(api.uploads[0].content)
    assert upload.tag == "osmChange"
    assert len(upload) == len(upload[0]) == 1
    assert upload[0].tag == "create"
    node = upload[0][0]
    assert node.attrib == {
        "id": "-1",
        "changeset": "77",
        "lat": "27.3329940",
        "lon": "33.6937310",
    }
    assert {tag.get("k"): tag.get("v") for tag in node} == {"shop": "supermarket"}
    stored = store.get(data["proposal_id"])
    assert stored.status == "APPLIED"
    assert stored.changeset_id == 77
    assert stored.receipt["node_id"] == 201
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert verified["success"], verified
    assert verified["data"]["node_id"] == 201
    assert verified["data"]["changeset_id"] == 77
    assert len(api.uploads) == 1


@pytest.mark.asyncio
async def test_repeat_apply_returns_receipt_without_elicitation_or_second_upload(
    workflow,
):
    api, _ = workflow
    data = await preview()
    first = await apply(data)
    assert first["success"], first
    context = ConfirmationContext(data["proposal_digest"])
    repeated = await apply(data, context)

    assert repeated["success"], repeated
    assert repeated["data"] == first["data"]
    assert context.messages == []
    assert len(api.changeset_creates) == len(api.uploads) == 1


@pytest.mark.asyncio
async def test_concurrent_confirmed_apply_claims_only_one_uploader(workflow):
    api, _ = workflow
    data = await preview()
    confirmations_ready = asyncio.Event()
    count = 0

    async def barrier():
        nonlocal count
        count += 1
        if count == 2:
            confirmations_ready.set()
        await asyncio.wait_for(confirmations_ready.wait(), timeout=2)

    contexts = [
        ConfirmationContext(data["proposal_digest"], callback=barrier) for _ in range(2)
    ]
    results = await asyncio.gather(*(apply(data, context) for context in contexts))

    assert sum(result["success"] for result in results) == 1, results
    assert len(api.changeset_creates) == len(api.uploads) == 1
    assert all(len(context.messages) == 1 for context in contexts)


@pytest.mark.asyncio
async def test_changed_map_context_after_confirmation_blocks_all_writes(workflow):
    api, store = workflow
    data = await preview()

    async def changed_context():
        api.map_xml = (
            '<osm><node id="2" version="1" lat="27.3329000" ' 'lon="33.6937000"/></osm>'
        )

    context = ConfirmationContext(data["proposal_digest"], callback=changed_context)
    result = await apply(data, context)

    assert result["success"] is False
    assert "changed after preview" in result["detail"]
    assert len(context.messages) == 1
    assert api.writes == []
    assert store.get(data["proposal_id"]).status == "FAILED"


@pytest.mark.asyncio
async def test_timeout_recovery_proves_created_node_without_reupload(workflow):
    api, store = workflow
    data = await preview()
    api.upload_exception = httpx.ReadTimeout("Upload outcome is unknown")
    result = await apply(data)

    assert result["success"], result
    assert result["data"]["node_id"] == 201
    assert result["data"]["changeset_id"] == 77
    assert result["data"]["reconciliation"]["status"] == "reconciled"
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert len(api.changeset_creates) == len(api.uploads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "download", ["<osmChange/>", 503, httpx.ReadTimeout("Download unavailable")]
)
async def test_timeout_with_empty_or_unavailable_download_requires_reconciliation(
    workflow, download
):
    api, store = workflow
    data = await preview()
    api.upload_exception = httpx.ReadTimeout("Upload outcome is unknown")
    api.download = download
    result = await apply(data)

    assert result["success"] is False
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    assert result["reconciliation"]["status"] == "unresolved"
    stored = store.get(data["proposal_id"])
    assert stored.status == "RECONCILE_REQUIRED"
    assert stored.changeset_id == 77
    context = ConfirmationContext(data["proposal_digest"])
    repeated = await apply(data, context)
    assert repeated["success"] is False
    assert context.messages == []
    assert len(api.changeset_creates) == len(api.uploads) == 1


@pytest.mark.asyncio
async def test_delayed_verify_resolves_unknown_upload_without_any_further_write(
    workflow,
):
    api, store = workflow
    data = await preview()
    api.upload_exception = httpx.ReadTimeout("Upload outcome is unknown")
    api.download = "<osmChange/>"
    result = await apply(data)
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    previous_writes = len(api.writes)
    api.download = f"<osmChange><create>{created_node_xml()}</create></osmChange>"
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])

    assert verified["success"], verified
    assert verified["data"]["node_id"] == 201
    assert verified["data"]["changeset_id"] == 77
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert len(api.writes) == previous_writes
    assert len(api.uploads) == 1
    context = ConfirmationContext(data["proposal_digest"])
    repeated = await apply(data, context)
    assert repeated["success"], repeated
    assert context.messages == []
    assert len(api.writes) == previous_writes


@pytest.mark.asyncio
@pytest.mark.parametrize("download", [503, httpx.ReadTimeout("Download unavailable")])
@pytest.mark.parametrize(
    "initial_changes", [{"lat": "27.3329941"}, {"tags": {"shop": "convenience"}}]
)
async def test_confirmed_mapping_survives_failed_readback_and_unavailable_download(
    workflow, download, initial_changes
):
    api, store = workflow
    data = await preview()
    api.node_xml = created_node_xml(**initial_changes)
    api.download = download
    result = await apply(data)

    assert result["success"] is False
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    stored = store.get(data["proposal_id"])
    assert stored.status == "RECONCILE_REQUIRED"
    assert stored.changeset_id == stored.receipt["changeset_id"] == 77
    assert stored.receipt["node_id"] == 201
    assert stored.receipt["diff_results"] == [
        {"type": "node", "old_id": -1, "new_id": 201, "new_version": 1}
    ]
    assert stored.receipt["verification"]["status"] == "verification_incomplete"
    context = ConfirmationContext(data["proposal_digest"])
    assert (await apply(data, context))["success"] is False
    assert context.messages == []
    assert len(api.changeset_creates) == len(api.uploads) == 1
    previous_writes = len(api.writes)
    previous_downloads = sum(
        request.url.path.endswith("/changeset/77/download") for request in api.requests
    )

    # Durable upload evidence permits recovery after a new process sees a good
    # node readback, even while changeset download remains unavailable.
    track_tools._PROPOSALS.clear()
    api.node_xml = created_node_xml()
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])

    assert verified["success"], verified
    assert verified["data"]["node_id"] == 201
    assert verified["data"]["changeset_id"] == 77
    recovered = store.get(data["proposal_id"])
    assert recovered.status == "APPLIED"
    assert recovered.receipt["node_id"] == 201
    assert recovered.receipt["reconciliation"]["evidence"] == (
        "confirmed upload mapping and exact node readback"
    )
    assert len(api.writes) == previous_writes
    assert (
        sum(
            request.url.path.endswith("/changeset/77/download")
            for request in api.requests
        )
        == previous_downloads
    )
    repeated_context = ConfirmationContext(data["proposal_digest"])
    repeated = await apply(data, repeated_context)
    assert repeated["success"], repeated
    assert repeated_context.messages == []
    assert len(api.writes) == previous_writes
    assert len(api.uploads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_root", ["osm", "osmChange"])
async def test_mapping_from_wrong_diff_root_is_not_trusted_for_delayed_recovery(
    workflow, wrong_root
):
    api, store = workflow
    data = await preview()
    api.upload_response = (
        f'<{wrong_root}><node old_id="-1" new_id="201" new_version="1"/>'
        f"</{wrong_root}>"
    )
    api.download = 503
    result = await apply(data)

    assert result["success"] is False
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    stored = store.get(data["proposal_id"])
    assert stored.status == "RECONCILE_REQUIRED"
    assert "node_id" not in stored.receipt
    assert stored.receipt["diff_results"] == []
    assert stored.receipt["verification"] is None
    previous_writes = len(api.writes)
    verified = await edit_tools.verify_osm_edit(data["proposal_id"])
    assert verified["success"] is False
    assert verified["status"] == "RECONCILE_REQUIRED"
    context = ConfirmationContext(data["proposal_digest"])
    repeated = await apply(data, context)
    assert repeated["success"] is False
    assert context.messages == []
    assert len(api.writes) == previous_writes
    assert len(api.changeset_creates) == len(api.uploads) == 1
    assert not any(request.url.path.endswith("/node/201") for request in api.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [{"lat": "27.3329941"}, {"tags": {"shop": "convenience"}}]
)
async def test_failed_created_node_readback_stays_uncertain_without_repeat_upload(
    workflow, changes
):
    api, store = workflow
    data = await preview()
    api.node_xml = created_node_xml(**changes)
    result = await apply(data)

    assert result["success"] is False
    assert result["proposal_status"] == "RECONCILE_REQUIRED"
    assert store.get(data["proposal_id"]).status == "RECONCILE_REQUIRED"
    assert len(api.uploads) == 1
    assert (await apply(data))["success"] is False
    assert len(api.uploads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [{"lon": "33.6937311"}, {"tags": {"shop": "convenience"}}]
)
async def test_verify_detects_later_coordinate_or_tag_mismatch(workflow, changes):
    api, store = workflow
    data = await preview()
    assert (await apply(data))["success"]
    previous_writes = len(api.writes)
    api.node_xml = created_node_xml(**changes)
    result = await edit_tools.verify_osm_edit(data["proposal_id"])

    assert result["success"] is False
    assert result["data"]["verification"]["status"] == "verification_incomplete"
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert len(api.writes) == previous_writes


@pytest.mark.asyncio
async def test_supplied_changeset_is_rejected_before_confirmation(workflow):
    api, _ = workflow
    data = await preview()
    context = ConfirmationContext(data["proposal_digest"])
    result = await apply(data, context, changeset_id=77)

    assert result["success"] is False
    assert result["error"] == "Dedicated changeset required"
    assert context.messages == []
    assert api.writes == []


@pytest.mark.asyncio
async def test_creation_still_requires_host_confirmation_when_dev_setting_is_disabled(
    workflow, monkeypatch
):
    api, _ = workflow
    data = await preview()
    monkeypatch.setattr(config, "osm_require_host_confirmation", False)
    context = ConfirmationContext(data["proposal_digest"], action="decline")
    result = await apply(data, context)

    assert result["success"] is False
    assert len(context.messages) == 1
    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("after_confirmation", [False, True])
async def test_persisted_payload_tampering_cannot_use_cached_approved_digest(
    workflow, after_confirmation
):
    api, store = workflow
    data = await preview()

    async def tamper():
        stored = store.get(data["proposal_id"])
        payload = stored.payload
        payload["create_nodes"][0]["tags"]["shop"] = "convenience"
        with store._connection() as connection:
            connection.execute(
                "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
                (json.dumps(payload), data["proposal_id"]),
            )

    context = ConfirmationContext(
        data["proposal_digest"], callback=tamper if after_confirmation else None
    )
    if not after_confirmation:
        await tamper()
    result = await apply(data, context)

    assert result["success"] is False
    assert "digest" in (result.get("detail", "") + result["error"]).lower()
    assert api.writes == []
