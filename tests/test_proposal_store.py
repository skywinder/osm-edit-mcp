import concurrent.futures

import pytest

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


def test_review_fields_do_not_change_proposal_digest(tmp_path):
    store = ProposalStore(tmp_path / "proposals.sqlite3")
    proposal = store.create(
        "proposal-1", _payload(), "https://api.example.test/api/0.6", None, 1800
    )
    updated = dict(proposal.payload)
    updated["_review"] = {"proposed_geojson": {"type": "FeatureCollection"}}

    store.update_payload(proposal.proposal_id, updated)

    assert store.get(proposal.proposal_id).digest == proposal.digest
