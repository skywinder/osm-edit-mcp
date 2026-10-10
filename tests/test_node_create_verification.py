"""A creation receipt needs exact, nonempty evidence; recovery never writes."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import httpx
import pytest

from src.osm_edit_mcp.config import config
from src.osm_edit_mcp.node_create_verification import (
    reconcile_node_create,
    verify_node_create,
)

PAYLOAD = {
    "action": "node_create",
    "create_nodes": [
        {
            "id": -1,
            "lat": "27.3329940",
            "lon": "33.6937310",
            "tags": {"shop": "supermarket"},
        }
    ],
    "create_ways": [],
    "modify_nodes": [],
    "modify_ways": [],
    "delete_nodes": [],
}
DIFF = [{"type": "node", "old_id": -1, "new_id": 123, "new_version": 1}]


def node_xml(*, tags=None, **attributes):
    values = {
        "id": "123",
        "version": "1",
        "changeset": "99",
        "visible": "true",
        "lat": "27.332994",
        "lon": "33.693731",
        **attributes,
    }
    element = ET.Element(
        "node", {k: str(v) for k, v in values.items() if v is not None}
    )
    for key, value in ([("shop", "supermarket")] if tags is None else tags):
        ET.SubElement(element, "tag", {"k": key, "v": value})
    return ET.tostring(element, encoding="unicode")


def readback_xml(**attributes):
    return f"<osm>{node_xml(**attributes)}</osm>"


def download_xml(**attributes):
    return f"<osmChange><create>{node_xml(**attributes)}</create></osmChange>"


class Response:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class ReadOnlyClient:
    """No upload method exists; all requests must match this explicit read list."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def get(self, url):
        self.requests.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_created_node_verified_with_complete_tags_and_numeric_coordinates():
    client = ReadOnlyClient(
        Response(readback_xml(lat="27.332994000", lon="33.6937310"))
    )
    result = await verify_node_create(client, DIFF, PAYLOAD, 99)

    assert result["status"] == "verified"
    assert len(result["verified"]) == 1
    assert result["verified"][0]["actual_version"] == 1
    assert result["failures"] == []
    assert client.requests == [f"{config.current_api_base_url}/node/123"]


@pytest.mark.parametrize(
    "diff",
    [
        [],
        DIFF * 2,
        [{**DIFF[0], "type": "way"}],
        [{**DIFF[0], "old_id": 1}],
        [{**DIFF[0], "old_id": "-1"}],
        [{**DIFF[0], "new_id": 0}],
        [{**DIFF[0], "new_id": -123}],
        [{**DIFF[0], "new_id": True}],
        [{**DIFF[0], "new_id": "123"}],
        [{**DIFF[0], "new_version": 2}],
        [{**DIFF[0], "new_version": True}],
        [{}],
        [None],
        None,
    ],
)
@pytest.mark.asyncio
async def test_missing_or_nonmatching_diff_cannot_verify_vacuously(diff):
    client = ReadOnlyClient()
    result = await verify_node_create(client, diff, PAYLOAD, 99)

    assert result["status"] == "verification_incomplete"
    assert result["verified"] == []
    assert result["failures"]
    assert client.requests == []


@pytest.mark.parametrize(
    "attributes",
    [
        {"id": "124"},
        {"id": None},
        {"id": "invalid"},
        {"version": "2"},
        {"version": None},
        {"changeset": "98"},
        {"changeset": None},
        {"visible": "false"},
        {"visible": None},
        {"visible": "TRUE"},
        {"lat": "27.33299401"},
        {"lon": "33.69373101"},
        {"lat": "NaN"},
        {"lon": "Infinity"},
        {"lat": "91"},
        {"lon": "181"},
        {"lat": None},
        {"lon": "invalid"},
        {"tags": []},
        {"tags": [("shop", "convenience")]},
        {"tags": [("shop", "supermarket"), ("name", "Unapproved")]},
        {"tags": [("shop", "supermarket"), ("shop", "supermarket")]},
    ],
)
@pytest.mark.asyncio
async def test_readback_requires_exact_id_version_changeset_visibility_coords_and_tags(
    attributes,
):
    client = ReadOnlyClient(Response(readback_xml(**attributes)))
    result = await verify_node_create(client, DIFF, PAYLOAD, 99)

    assert result["status"] == "verification_incomplete"
    assert result["verified"] == []
    assert result["failures"][0]["verification_error"]


@pytest.mark.parametrize(
    "xml",
    [
        "<osm/>",
        f"<wrong>{node_xml()}</wrong>",
        f"<osm>{node_xml()}{node_xml()}</osm>",
        f"<osm><create>{node_xml()}</create></osm>",
        f"<osm>{node_xml()}<way id='5'/></osm>",
        "<osm><node>",
        '<!DOCTYPE osm [<!ENTITY data "private">]><osm>&data;</osm>',
        "<osm><node id='123' version='1' changeset='99' visible='true' "
        "lat='27.332994' lon='33.693731'><tag k='shop'/></node></osm>",
        "<osm><node id='123' version='1' changeset='99' visible='true' "
        "lat='27.332994' lon='33.693731'><tag k='shop' v='supermarket'>"
        "<node/></tag></node></osm>",
    ],
)
@pytest.mark.asyncio
async def test_missing_multiple_nested_or_unsafe_readback_xml_is_incomplete(xml):
    result = await verify_node_create(ReadOnlyClient(Response(xml)), DIFF, PAYLOAD, 99)

    assert result["status"] == "verification_incomplete"
    assert result["verified"] == []
    assert result["failures"]


@pytest.mark.parametrize("response", [Response(status_code=404), httpx.ReadTimeout("")])
@pytest.mark.asyncio
async def test_unavailable_readback_does_not_verify(response):
    result = await verify_node_create(ReadOnlyClient(response), DIFF, PAYLOAD, 99)

    assert result["status"] == "verification_incomplete"
    assert result["failures"][0]["verification_error"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(create_nodes=[]),
        lambda payload: payload["create_nodes"].append(payload["create_nodes"][0]),
        lambda payload: payload.update(create_ways=[{"id": -2}]),
        lambda payload: payload.update(modify_nodes=[{"id": 123}]),
        lambda payload: payload.update(modify_ways=[{"id": 123}]),
        lambda payload: payload.update(delete_nodes=[{"id": 123}]),
        lambda payload: payload["create_nodes"][0].update(id=-2),
        lambda payload: payload["create_nodes"][0].update(tags={}),
        lambda payload: payload["create_nodes"][0].update(tags={"shop": True}),
        lambda payload: payload["create_nodes"][0].update(lat="27.33299401"),
        lambda payload: payload["create_nodes"][0].update(lon=True),
    ],
)
@pytest.mark.asyncio
async def test_verification_rejects_malformed_approved_creation_payload(mutation):
    payload = deepcopy(PAYLOAD)
    mutation(payload)
    client = ReadOnlyClient()
    result = await verify_node_create(client, DIFF, payload, 99)

    assert result["status"] == "verification_incomplete"
    assert client.requests == []


@pytest.mark.parametrize("changeset_id", [0, -1, True, "99", None])
@pytest.mark.asyncio
async def test_verification_requires_recorded_positive_changeset_id(changeset_id):
    client = ReadOnlyClient()
    result = await verify_node_create(client, DIFF, PAYLOAD, changeset_id)

    assert result["status"] == "verification_incomplete"
    assert client.requests == []


@pytest.mark.asyncio
async def test_recovery_proves_exact_changeset_download_and_independent_node_readback():
    client = ReadOnlyClient(
        Response(download_xml(visible=None)), Response(readback_xml())
    )
    result = await reconcile_node_create(client, PAYLOAD, 99)

    assert result["status"] == "reconciled"
    assert result["diff_results"] == DIFF
    assert result["verification"]["status"] == "verified"
    assert client.requests == [
        f"{config.current_api_base_url}/changeset/99/download",
        f"{config.current_api_base_url}/node/123",
    ]


@pytest.mark.parametrize(
    "xml",
    [
        "<osmChange/>",
        "<osmChange><create/></osmChange>",
        f"<osm>{node_xml()}</osm>",
        f"<osmChange><create>{node_xml()}{node_xml()}</create></osmChange>",
        f"<osmChange><modify>{node_xml()}</modify></osmChange>",
        f"<osmChange><create>{node_xml()}<way id='124'/></create></osmChange>",
        f"<osmChange><create>{node_xml()}</create><delete/></osmChange>",
        download_xml(id="-1"),
        download_xml(version="2"),
        download_xml(changeset="98"),
        download_xml(lat="27.33299401"),
        download_xml(tags=[("shop", "convenience")]),
        download_xml(tags=[("shop", "supermarket"), ("shop", "supermarket")]),
        download_xml(visible="false"),
        "<osmChange><create>",
        '<!DOCTYPE osmChange [<!ENTITY data "private">]><osmChange>&data;</osmChange>',
    ],
)
@pytest.mark.asyncio
async def test_uncertain_download_never_authorizes_recovery_or_blind_retry(xml):
    client = ReadOnlyClient(Response(xml))
    result = await reconcile_node_create(client, PAYLOAD, 99)

    assert result["status"] == "unresolved"
    assert "diff_results" not in result
    assert len(client.requests) == 1


@pytest.mark.parametrize("response", [Response(status_code=503), httpx.ReadTimeout("")])
@pytest.mark.asyncio
async def test_unavailable_download_leaves_outcome_unresolved(response):
    client = ReadOnlyClient(response)
    result = await reconcile_node_create(client, PAYLOAD, 99)

    assert result["status"] == "unresolved"
    assert result["error"]
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    "response",
    [Response(readback_xml(tags=[])), Response(status_code=404), httpx.ReadTimeout("")],
)
@pytest.mark.asyncio
async def test_matching_changeset_without_verified_readback_remains_unresolved(
    response,
):
    client = ReadOnlyClient(Response(download_xml()), response)
    result = await reconcile_node_create(client, PAYLOAD, 99)

    assert result["status"] == "unresolved"
    assert result["verification"]["status"] == "verification_incomplete"
    assert "diff_results" not in result
    assert len(client.requests) == 2
