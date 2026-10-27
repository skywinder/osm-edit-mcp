"""Duplicate decisions are bounded, versioned previews, never write approval."""

import asyncio
import json
from copy import deepcopy

import pytest

from src.osm_edit_mcp import node_tools, track_tools
from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.poi_duplicates import POLICY, geometry_distance
from src.osm_edit_mcp.proposal_store import canonical_digest
from tests.test_node_create_apply import (
    ConfirmationContext,
    apply,
    created_node_xml,
    workflow,
)
from tests.test_node_create_preview import node_create_client, preview

PITCH_TAGS = {"leisure": "pitch", "sport": "volleyball", "surface": "sand"}
ACCEPTANCE_XML = """<osm>
<node id="10" version="1" lat="27.2433" lon="33.84426"><tag k="leisure" v="swimming_pool"/></node>
<node id="11" version="1" lat="27.2434" lon="33.84426"><tag k="leisure" v="swimming_pool"/></node>
<node id="12" version="1" lat="27.2435" lon="33.84426"><tag k="leisure" v="swimming_pool"/></node>
<node id="20" version="1" lat="27.2429" lon="33.8439"/>
<node id="21" version="1" lat="27.2438" lon="33.8439"/>
<node id="22" version="1" lat="27.2438" lon="33.8449"/>
<node id="23" version="1" lat="27.2429" lon="33.8449"/>
<way id="40" version="4"><nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="20"/>
<tag k="leisure" v="beach_resort"/></way>
<node id="30" version="1" lat="27.24318" lon="33.84445"/>
<node id="31" version="1" lat="27.24329" lon="33.84445"/>
<node id="32" version="1" lat="27.24329" lon="33.8447"/>
<node id="33" version="1" lat="27.24318" lon="33.8447"/>
<way id="50" version="3"><nd ref="30"/><nd ref="31"/><nd ref="32"/><nd ref="33"/><nd ref="30"/>
<tag k="leisure" v="pitch"/><tag k="sport" v="tennis"/></way>
</osm>"""


def decision(candidate=None, **overrides):
    values = {
        "osm_type": "way",
        "osm_id": 50,
        "expected_version": 3,
        "decision": "distinct_object",
        "reason": "Отдельный волейбольный корт перед бассейнами, теннисный корт восточнее",
        "evidence_source": "user report from on-site observation",
    }
    if candidate:
        values.update(
            osm_type=candidate["type"],
            osm_id=candidate["id"],
            expected_version=candidate["version"],
        )
    values.update(overrides)
    return values


async def pitch_preview():
    return await preview(latitude=27.243239, longitude=33.84426, tags=PITCH_TAGS)


async def review(data, decisions=None, **overrides):
    arguments = {
        "proposal_id": data["proposal_id"],
        "proposal_digest": data["proposal_digest"],
        "decisions": [decision()] if decisions is None else decisions,
    }
    arguments.update(overrides)
    return await node_tools.review_node_create_duplicates(**arguments)


def candidate(tags, distance_lat=0, geometry=None):
    return {
        "type": "node",
        "id": 100,
        "version": 2,
        "tags": tags,
        "geometry": geometry
        or {"type": "Point", "coordinates": [33.84426, 27.243239 + distance_lat]},
    }


def classify(tags, distance_lat=0, geometry=None, proposed=None):
    node = {"lat": "27.2432390", "lon": "33.8442600", "tags": proposed or PITCH_TAGS}
    return node_tools._review_candidates(
        [candidate(tags, distance_lat, geometry)], node
    )[0]


@pytest.mark.parametrize("kind", ["swimming_pool", "beach_resort"])
def test_different_leisure_types_are_context_even_at_same_position(kind):
    item = classify({"leisure": kind})
    assert item["classification"] == "context_only"
    assert item["blocking"] is False
    assert item["reasons"]
    assert "potential_duplicate" not in item


@pytest.mark.parametrize(
    "sport",
    [None, "multi", "unknown", "tennis;volleyball", "volleyball;basketball", "tennis"],
)
def test_nearby_pitch_is_not_excluded_by_missing_multi_list_or_different_sport(sport):
    tags = {"leisure": "pitch"}
    if sport is not None:
        tags["sport"] = sport
    item = classify(tags, 0.0001)  # 11 m, outside generic likely threshold
    assert item["blocking"]
    assert item["classification"] == (
        "likely_duplicate" if sport and "volleyball" in sport else "possible_duplicate"
    )
    assert any("sport" in reason.lower() for reason in item["reasons"])


def test_true_duplicate_remains_likely_despite_different_name_and_sport():
    item = classify(
        {"leisure": "pitch", "sport": "tennis", "name": "Old name"},
        proposed={**PITCH_TAGS, "name": "New name"},
    )
    assert item["classification"] == "likely_duplicate"
    assert item["blocking"]
    assert any("renaming" in reason for reason in item["reasons"])


@pytest.mark.parametrize(
    "identity",
    [{"name": "Court A"}, {"phone": "+20 123 456"}, {"website": "https://example.org"}],
)
def test_name_and_contacts_raise_suspicion_outside_type_distance(identity):
    item = classify(
        {**PITCH_TAGS, **identity}, 0.0007, proposed={**PITCH_TAGS, **identity}
    )
    assert item["classification"] == "likely_duplicate"
    assert item["distance_m"] > POLICY["leisure=pitch"]["possible_m"]


def test_sports_reduce_likelihood_but_do_not_prove_distinctness():
    assert classify(PITCH_TAGS, 0.0001)["classification"] == "likely_duplicate"
    assert (
        classify({"leisure": "pitch", "sport": "tennis"}, 0.0001)["classification"]
        == "possible_duplicate"
    )
    assert (
        classify({"leisure": "pitch", "sport": "tennis"}, 0.0007)["classification"]
        == "context_only"
    )


def test_overlapping_pitch_uses_area_not_centroid_and_containing_resort_is_context():
    # Centroid is hundreds of metres away; the point is inside a corner.
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [33.8442, 27.2432],
                [33.8542, 27.2432],
                [33.8542, 27.2532],
                [33.8442, 27.2532],
                [33.8442, 27.2432],
            ]
        ],
    }
    item = classify({"leisure": "pitch", "sport": "tennis"}, geometry=polygon)
    assert item["distance_m"] == 0
    assert item["classification"] == "likely_duplicate"
    resort = classify({"leisure": "beach_resort"}, geometry=polygon)
    assert resort["classification"] == "context_only"
    assert any("intersects" in reason for reason in item["reasons"])


def test_distance_to_polygon_edge_and_hole():
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]],
            [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6], [0.4, 0.4]],
        ],
    }
    assert geometry_distance(polygon, (0.2, 0.2)) == 0
    assert geometry_distance(polygon, (0.5, 0.5)) > 1000
    assert 10 < geometry_distance(polygon, (0.2, -0.0001)) < 12


@pytest.mark.asyncio
async def test_acceptance_preview_revision_and_no_osm_mutations(node_create_client):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    candidates = original["duplicate_search"]["candidates"]
    assert len(candidates) == 5
    assert [item["blocking"] for item in candidates] == [
        False,
        False,
        False,
        False,
        True,
    ]
    assert candidates[-1]["classification"] == "possible_duplicate"
    assert original["duplicate_search"]["policy"] == POLICY
    result = await review(original)
    assert result["success"], result
    data = result["data"]
    store = track_tools._PROPOSAL_STORE
    parent = store.get(original["proposal_id"])
    revision = store.get(data["proposal_id"])
    assert parent.status == "SUPERSEDED"
    assert parent.payload["_superseded_by"] == revision.proposal_id
    assert data["proposal_digest"] != original["proposal_digest"]
    assert data["revision"] == {
        "number": 2,
        "supersedes_proposal_id": parent.proposal_id,
        "supersedes_proposal_digest": parent.digest,
    }
    assert data["duplicate_decisions"] == [decision()]
    assert data["confirmation_required"] is True
    assert data["operations"] == original["operations"]
    assert data["operations"]["create_nodes"] == [
        {"id": -1, "lat": "27.2432390", "lon": "33.8442600", "tags": PITCH_TAGS}
    ]
    assert revision.digest == canonical_digest(
        revision.payload, revision.api_target, revision.osm_uid
    )
    assert revision.expires_at >= parent.expires_at
    assert data["duplicate_search"]["blocking_duplicate_count"] == 0
    assert (
        data["duplicate_search"]["candidates"][-1]["classification"]
        == "possible_duplicate"
    )
    assert data["duplicate_search"]["candidates"][-1]["blocking"] is False
    assert all(
        item["osm_url"] == f"{config.current_web_base_url}/{item['type']}/{item['id']}"
        for item in candidates
    )
    assert data["web_preview_url"] is None
    assert "internal MCP" in data["web_preview_status"]
    page = track_tools.proposal_preview_resource(data["proposal_id"])
    assert '"dismissed"' in page and '"suspected"' in page and '"proposed"' in page
    assert decision()["reason"] in page
    assert decision()["evidence_source"] in page
    assert "SUPERSEDED" in track_tools.proposal_preview_resource(
        original["proposal_id"]
    )
    assert all(request.method == "GET" for request in node_create_client["requests"])
    track_tools._PROPOSALS.clear()
    async with track_tools.get_authenticated_client() as client:
        await node_tools.validate_node_create_context(client, revision.payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["same_object", "uncertain"])
async def test_same_and_uncertain_stay_blocked_and_can_be_rereviewed(
    node_create_client, kind
):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    result = await review(original, [decision(decision=kind)])
    assert not result["success"]
    data = result["data"]
    assert data["blocking_issues"]
    if kind == "same_object":
        assert any("edit the existing" in issue for issue in data["blocking_issues"])
    async with track_tools.get_authenticated_client() as client:
        with pytest.raises(ValueError, match="unresolved"):
            await node_tools.validate_node_create_context(
                client, track_tools._get_proposal(data["proposal_id"]).payload
            )
    rereview = await review(data)
    assert rereview["success"], rereview
    assert rereview["data"]["revision"]["number"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        [],
        [decision(osm_id=999)],
        [decision(osm_type="node")],
        [decision(expected_version=4)],
        [decision(), decision()],
        [decision(reason=" ")],
        [decision(evidence_source="")],
        [decision(evidence_source="Google Maps")],
        [decision(decision="force")],
        [decision(osm_id=True)],
        [decision(expected_version="3")],
        [decision(skip_duplicate_check=True)],
    ],
)
async def test_invalid_or_incomplete_decisions_do_not_replace_parent(
    node_create_client, values
):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    result = await review(original, values)
    assert not result["success"]
    assert "data" not in result
    assert (
        track_tools._PROPOSAL_STORE.get(original["proposal_id"]).status == "PREVIEWED"
    )
    assert len(track_tools._PROPOSAL_STORE.list()) == 1
    assert all(request.method == "GET" for request in node_create_client["requests"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["version", "geometry", "new_duplicate", "incomplete", "failure"]
)
async def test_review_rejects_changed_or_incomplete_search(node_create_client, change):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    if change == "version":
        node_create_client["xml"] = ACCEPTANCE_XML.replace(
            'way id="50" version="3"', 'way id="50" version="4"'
        )
    elif change == "geometry":
        node_create_client["xml"] = ACCEPTANCE_XML.replace(
            'lat="27.24318"', 'lat="27.24319"'
        )
    elif change == "new_duplicate":
        node_create_client["xml"] = ACCEPTANCE_XML.replace(
            "</osm>",
            '<node id="99" version="1" lat="27.243239" lon="33.84426"><tag k="leisure" v="pitch"/></node></osm>',
        )
    elif change == "incomplete":
        node_create_client["xml"] = "<osm><remark>truncated</remark></osm>"
    else:
        node_create_client["status"] = 503
    result = await review(original)
    assert not result["success"]
    assert (
        track_tools._PROPOSAL_STORE.get(original["proposal_id"]).status == "PREVIEWED"
    )


@pytest.mark.asyncio
async def test_review_digest_expiry_and_superseded_are_rejected(
    node_create_client, monkeypatch
):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    result = await review(original, proposal_digest="0" * 64)
    assert not result["success"] and "digest" in result["detail"]
    assert len(node_create_client["requests"]) == 1
    result = await review(original)
    assert result["success"]
    assert not (await review(original))["success"]
    revision = result["data"]
    monkeypatch.setattr(
        track_tools.time, "time", lambda: revision["expires_at_unix"] + 1
    )
    assert not (await review(revision))["success"]


@pytest.mark.asyncio
async def test_concurrent_reviews_only_one_revision_wins(node_create_client):
    node_create_client["xml"] = ACCEPTANCE_XML
    original = (await pitch_preview())["data"]
    results = await asyncio.gather(review(original), review(original))
    assert sum(result["success"] for result in results) == 1
    assert len(track_tools._PROPOSAL_STORE.list()) == 2


async def workflow_review(api):
    api.map_xml = ACCEPTANCE_XML
    result = await pitch_preview()
    original = result["data"]
    result = await review(original)
    assert result["success"], result
    return original, result["data"]


@pytest.mark.asyncio
async def test_reviewed_acceptance_uploads_only_new_node_after_final_confirmation(
    workflow,
):
    api, store = workflow
    original, data = await workflow_review(api)
    assert not api.writes
    api.node_xml = created_node_xml(lat="27.2432390", lon="33.8442600", tags=PITCH_TAGS)
    context = ConfirmationContext(data["proposal_digest"])
    assert not (await apply(original, context))["success"]
    assert not context.messages
    result = await apply(data, context)
    assert result["success"], result
    assert len(context.messages) == 1
    assert data["proposal_digest"] in context.messages[0]
    assert decision()["reason"] in context.messages[0]
    assert decision()["evidence_source"] in context.messages[0]
    assert len(api.uploads) == 1
    upload = api.uploads[0].content.decode()
    assert "<modify" not in upload and "<delete" not in upload and "<way" not in upload
    assert store.get(data["proposal_id"]).status == "APPLIED"
    assert store.get(original["proposal_id"]).status == "SUPERSEDED"


@pytest.mark.asyncio
async def test_true_duplicate_blocks_creation_and_no_blocker_can_be_omitted(workflow):
    api, store = workflow
    api.map_xml = ACCEPTANCE_XML.replace(
        "</osm>",
        '<node id="99" version="2" lat="27.243239" lon="33.84426">'
        '<tag k="leisure" v="pitch"/><tag k="sport" v="volleyball"/></node></osm>',
    )
    result = await pitch_preview()
    assert not result["success"]
    original = result["data"]
    duplicate = next(
        item for item in original["duplicate_search"]["candidates"] if item["id"] == 99
    )
    assert duplicate["classification"] == "likely_duplicate"
    assert not (await review(original))[
        "success"
    ]  # tennis decision alone is incomplete
    assert store.get(original["proposal_id"]).status == "PREVIEWED"
    result = await review(
        original, [decision(), decision(duplicate, decision="same_object")]
    )
    assert not result["success"]
    data = result["data"]
    assert any("edit the existing" in issue for issue in data["blocking_issues"])
    context = ConfirmationContext(data["proposal_digest"])
    assert not (await apply(data, context))["success"]
    assert not context.messages and not api.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "version",
        "new_duplicate",
        "incomplete",
        "digest",
        "expired",
        "decline",
        "old_digest",
    ],
)
async def test_review_does_not_bypass_apply_safety(workflow, monkeypatch, change):
    api, store = workflow
    original, data = await workflow_review(api)

    async def mutate():
        if change == "version":
            api.map_xml = ACCEPTANCE_XML.replace(
                'way id="50" version="3"', 'way id="50" version="4"'
            )
        elif change == "new_duplicate":
            api.map_xml = ACCEPTANCE_XML.replace(
                "</osm>",
                '<node id="99" version="1" lat="27.243239" lon="33.84426"><tag k="leisure" v="pitch"/><tag k="sport" v="volleyball"/></node></osm>',
            )
        elif change == "incomplete":
            api.map_xml = "<osm><remark>truncated</remark></osm>"
        elif change == "digest":
            stored = store.get(data["proposal_id"])
            payload = deepcopy(stored.payload)
            payload["duplicate_decisions"][0]["reason"] = "Different evidence"
            with store._connection() as connection:
                connection.execute(
                    "UPDATE proposals SET payload_json=? WHERE proposal_id=?",
                    (json.dumps(payload), data["proposal_id"]),
                )
        elif change == "expired":
            monkeypatch.setattr(
                track_tools.time, "time", lambda: data["expires_at_unix"] + 1
            )

    context = ConfirmationContext(
        (
            original["proposal_digest"]
            if change == "old_digest"
            else data["proposal_digest"]
        ),
        action="decline" if change == "decline" else "accept",
        callback=mutate,
    )
    result = await apply(data, context)
    assert not result["success"], result
    assert len(context.messages) == 1
    assert api.writes == []


@pytest.mark.asyncio
async def test_revision_created_during_confirmation_invalidates_old_approval(workflow):
    api, store = workflow
    _, data = await workflow_review(api)
    revised = []

    async def revise():
        revised.append(await review(data))

    context = ConfirmationContext(data["proposal_digest"], callback=revise)
    result = await apply(data, context)
    assert revised[0]["success"]
    assert not result["success"]
    assert store.get(data["proposal_id"]).status == "SUPERSEDED"
    assert api.writes == []
