import concurrent.futures
import json

import pytest

from src.osm_edit_mcp import proposal_store
from src.osm_edit_mcp.proposal_store import ProposalStore, ProposalStoreError


def _payload():
    return {
        "action": "create",
        "create_nodes": [{"id": -1, "lat": 1.0, "lon": 2.0}],
        "create_ways": [],
        "modify_ways": [],
        "delete_nodes": [],
    }


def test_proposal_claim_is_atomic_and_idempotent(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )

    def claim():
        try:
            return store.claim(
                proposal.proposal_id,
                proposal.digest,
                proposal.api_target,
                7,
            ).status
        except ProposalStoreError as exc:
            return str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    assert results.count("APPLYING") == 1
    assert (
        sum(result != "APPLYING" and "applying" in result.lower() for result in results)
        == 1
    )

    receipt = {"changeset_id": 123, "diff_results": []}
    store.finish(proposal.proposal_id, "APPLIED", receipt=receipt)
    repeated = store.claim(
        proposal.proposal_id, proposal.digest, proposal.api_target, 7
    )
    assert repeated.status == "APPLIED"
    assert repeated.receipt == receipt


def test_revision_and_upload_claim_compete_atomically(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    parent = store.create(
        "parent", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )

    def claim():
        try:
            store.claim(parent.proposal_id, parent.digest, parent.api_target, 7)
            return "claimed"
        except ProposalStoreError:
            return "blocked"

    def revise():
        try:
            store.supersede_preview(
                parent.proposal_id,
                parent.digest,
                "revision",
                _payload(),
                parent.api_target,
                7,
                1800,
            )
            return "revised"
        except ProposalStoreError:
            return "blocked"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda operation: operation(), [claim, revise]))

    assert results.count("blocked") == 1
    if "revised" in results:
        assert store.get("parent").status == "SUPERSEDED"
        assert store.get("revision").status == "PREVIEWED"
    else:
        assert store.get("parent").status == "APPLYING"
        assert store.get("revision") is None


@pytest.mark.parametrize(
    ("digest", "api_target", "uid", "message"),
    [
        ("wrong", "https://api.example.test/api/0.6", 7, "digest"),
        (None, "https://other.example.test/api/0.6", 7, "API target"),
        (None, "https://api.example.test/api/0.6", 8, "OSM account"),
    ],
)
def test_proposal_claim_is_bound_to_content_environment_and_actor(
    tmp_path, digest, api_target, uid, message
):
    store = ProposalStore(tmp_path / f"{uid}.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )

    with pytest.raises(ProposalStoreError, match=message):
        store.claim(
            proposal.proposal_id,
            digest or proposal.digest,
            api_target,
            uid,
        )


@pytest.mark.parametrize(
    ("digest", "api_target", "uid", "message"),
    [
        ("wrong", "https://api.example.test/api/0.6", 7, "digest"),
        (None, "https://other.example.test/api/0.6", 7, "API target"),
        (None, "https://api.example.test/api/0.6", 8, "OSM account"),
    ],
)
def test_applied_receipt_remains_bound_to_digest_environment_and_actor(
    tmp_path, digest, api_target, uid, message
):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )
    store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    store.finish(proposal.proposal_id, "APPLIED", receipt={"changeset_id": 123})

    with pytest.raises(ProposalStoreError, match=message):
        store.claim(proposal.proposal_id, digest or proposal.digest, api_target, uid)


@pytest.mark.parametrize("applied", [False, True])
def test_claim_detects_persisted_write_content_changed_without_digest(
    tmp_path, applied
):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )
    if applied:
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
        store.finish(proposal.proposal_id, "APPLIED", receipt={"changeset_id": 123})
    changed = _payload()
    changed["create_nodes"][0]["lat"] = 1.5
    with store._connection() as connection:
        connection.execute(
            "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
            (json.dumps(changed), proposal.proposal_id),
        )

    with pytest.raises(ProposalStoreError, match="digest mismatch"):
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)


def test_applying_proposal_does_not_expire_or_become_reclaimable(tmp_path, monkeypatch):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1
    )
    store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    monkeypatch.setattr(proposal_store.time, "time", lambda: proposal.expires_at + 1)

    assert store.get(proposal.proposal_id).status == "APPLYING"
    with pytest.raises(ProposalStoreError, match="applying"):
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    assert store.get(proposal.proposal_id).status == "APPLYING"
    store.finish(proposal.proposal_id, "APPLIED", receipt={"changeset_id": 123})
    assert store.get(proposal.proposal_id).status == "APPLIED"


@pytest.mark.parametrize("awaiting_approval", [False, True])
def test_unclaimed_preview_expires_at_ttl(tmp_path, monkeypatch, awaiting_approval):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1
    )
    if awaiting_approval:
        store.mark_awaiting_approval(proposal.proposal_id)
    monkeypatch.setattr(proposal_store.time, "time", lambda: proposal.expires_at)

    with pytest.raises(ProposalStoreError, match="expired"):
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    assert store.get(proposal.proposal_id) is None
    assert store.get(proposal.proposal_id, include_expired=True).status == "EXPIRED"


def test_expiration_read_does_not_overwrite_an_intervening_upload_claim(
    tmp_path, monkeypatch
):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1
    )
    intervened = False

    def race_clock():
        nonlocal intervened
        if not intervened:
            intervened = True
            store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
            return proposal.expires_at
        return proposal.created_at

    monkeypatch.setattr(proposal_store.time, "time", race_clock)

    assert store.get(proposal.proposal_id).status == "APPLYING"
    assert store.get(proposal.proposal_id).status == "APPLYING"


def test_claim_preserves_digest_when_preview_has_no_bound_account(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", None, 1800
    )
    claimed = store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    assert claimed.osm_uid is None
    store.finish(proposal.proposal_id, "APPLIED", receipt={"changeset_id": 123})
    assert (
        store.claim(
            proposal.proposal_id, proposal.digest, proposal.api_target, 7
        ).status
        == "APPLIED"
    )


def test_review_fields_do_not_change_proposal_digest(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", None, 1800
    )
    updated = dict(proposal.payload)
    updated["_review"] = {"proposed_geojson": {"type": "FeatureCollection"}}

    store.update_payload(proposal.proposal_id, updated)

    assert store.get(proposal.proposal_id).digest == proposal.digest
    assert store.get(proposal.proposal_id).payload["_review"] == updated["_review"]


def test_derived_update_refuses_write_content_changes(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )
    updated = _payload()
    updated["create_nodes"][0]["lat"] = 1.5
    updated["_review"] = {"label": "changed"}

    with pytest.raises(ProposalStoreError, match="cannot change.*digest"):
        store.update_payload(proposal.proposal_id, updated)
    assert store.get(proposal.proposal_id).payload == proposal.payload


@pytest.mark.parametrize("status", ["AWAITING_APPROVAL", "APPLYING", "APPLIED"])
def test_derived_update_refuses_proposals_after_review_started(tmp_path, status):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )
    if status == "AWAITING_APPROVAL":
        store.mark_awaiting_approval(proposal.proposal_id)
    else:
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
        if status == "APPLIED":
            store.finish(proposal.proposal_id, status, receipt={"changeset_id": 123})
    updated = dict(proposal.payload)
    updated["_review"] = {"label": "too late"}

    with pytest.raises(ProposalStoreError, match="Only a previewed proposal"):
        store.update_payload(proposal.proposal_id, updated)
    assert store.get(proposal.proposal_id).payload == proposal.payload


def _uncertain_upload(tmp_path, ttl_seconds=1800):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, ttl_seconds
    )
    store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
    store.set_changeset_id(proposal.proposal_id, 123)
    store.finish(
        proposal.proposal_id,
        "RECONCILE_REQUIRED",
        receipt={"changeset_id": 123},
        error="Upload timed out",
    )
    return store, proposal


def test_reconciliation_persists_receipt_after_preview_ttl(tmp_path, monkeypatch):
    store, proposal = _uncertain_upload(tmp_path, ttl_seconds=1)
    monkeypatch.setattr(proposal_store.time, "time", lambda: proposal.expires_at + 1)
    receipt = {"changeset_id": 123, "node_id": 456, "verification": "verified"}

    resolved = store.record_reconciliation(
        proposal.proposal_id, proposal.digest, proposal.api_target, 7, receipt
    )

    assert resolved.status == "APPLIED"
    assert resolved.receipt == receipt
    assert resolved.error is None
    assert store.get(proposal.proposal_id).receipt == receipt


@pytest.mark.parametrize(
    ("digest", "api_target", "uid", "message"),
    [
        ("wrong", "https://api.example.test/api/0.6", 7, "digest"),
        (None, "https://other.example.test/api/0.6", 7, "API target"),
        (None, "https://api.example.test/api/0.6", 8, "OSM account"),
    ],
)
def test_reconciliation_remains_bound_to_digest_environment_and_actor(
    tmp_path, digest, api_target, uid, message
):
    store, proposal = _uncertain_upload(tmp_path)

    with pytest.raises(ProposalStoreError, match=message):
        store.record_reconciliation(
            proposal.proposal_id,
            digest or proposal.digest,
            api_target,
            uid,
            {"changeset_id": 123},
        )
    assert store.get(proposal.proposal_id).status == "RECONCILE_REQUIRED"


@pytest.mark.parametrize("receipt_changeset", [None, 124, -1, "123", True])
def test_reconciliation_refuses_other_or_invalid_changesets(
    tmp_path, receipt_changeset
):
    store, proposal = _uncertain_upload(tmp_path)

    with pytest.raises(ProposalStoreError, match="different changeset"):
        store.record_reconciliation(
            proposal.proposal_id,
            proposal.digest,
            proposal.api_target,
            7,
            {"changeset_id": receipt_changeset},
        )
    assert store.get(proposal.proposal_id).status == "RECONCILE_REQUIRED"


def test_reconciliation_requires_a_persisted_upload_changeset(tmp_path):
    store, proposal = _uncertain_upload(tmp_path)
    with store._connection() as connection:
        connection.execute(
            "UPDATE proposals SET changeset_id=NULL WHERE proposal_id=?",
            (proposal.proposal_id,),
        )

    with pytest.raises(ProposalStoreError, match="different changeset"):
        store.record_reconciliation(
            proposal.proposal_id,
            proposal.digest,
            proposal.api_target,
            7,
            {"changeset_id": 123},
        )


def test_reconciliation_detects_persisted_write_content_tampering(tmp_path):
    store, proposal = _uncertain_upload(tmp_path)
    changed = _payload()
    changed["create_nodes"][0]["lon"] = 2.5
    with store._connection() as connection:
        connection.execute(
            "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
            (json.dumps(changed), proposal.proposal_id),
        )

    with pytest.raises(ProposalStoreError, match="digest mismatch"):
        store.record_reconciliation(
            proposal.proposal_id,
            proposal.digest,
            proposal.api_target,
            7,
            {"changeset_id": 123},
        )


@pytest.mark.parametrize("status", ["PREVIEWED", "APPLYING", "FAILED", "EXPIRED"])
def test_reconciliation_does_not_resolve_other_proposal_states(tmp_path, status):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", 7, 1800
    )
    store.set_changeset_id(proposal.proposal_id, 123)
    if status in {"APPLYING", "FAILED"}:
        store.claim(proposal.proposal_id, proposal.digest, proposal.api_target, 7)
        if status == "FAILED":
            store.finish(proposal.proposal_id, "FAILED")
    elif status == "EXPIRED":
        store.expire(proposal.proposal_id)

    with pytest.raises(ProposalStoreError, match="requiring reconciliation"):
        store.record_reconciliation(
            proposal.proposal_id,
            proposal.digest,
            proposal.api_target,
            7,
            {"changeset_id": 123},
        )
    assert store.get(proposal.proposal_id, include_expired=True).status == status


def test_concurrent_reconciliation_preserves_the_first_final_receipt(tmp_path):
    store, proposal = _uncertain_upload(tmp_path)

    def reconcile(marker):
        return store.record_reconciliation(
            proposal.proposal_id,
            proposal.digest,
            proposal.api_target,
            7,
            {"changeset_id": 123, "node_id": 456, "marker": marker},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(reconcile, ["first", "second"]))

    assert first.status == second.status == "APPLIED"
    assert first.receipt == second.receipt
    assert store.get(proposal.proposal_id).receipt == first.receipt
