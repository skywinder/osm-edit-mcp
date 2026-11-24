"""Verify a GPX road upload against the approved operations and OSM history."""

from decimal import Decimal
from typing import Any, Sequence

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config
from .http_client import describe_exception
from .node_create_verification import _coordinate, _exact_tags, _positive_id
from .proposal_store import StoredProposal, canonical_digest

ElementKey = tuple[str, int]
Record = dict[str, Any]


def _road_operations(payload: Record) -> dict[ElementKey, tuple[str, Record]]:
    if payload.get("action") not in {"create", "update"} or payload.get("modify_nodes"):
        raise ValueError("Expected a GPX road proposal")
    operations = {}
    for name, kind, action in (
        ("create_nodes", "node", "create"),
        ("create_ways", "way", "create"),
        ("modify_ways", "way", "modify"),
        ("delete_nodes", "node", "delete"),
    ):
        for element in payload[name]:
            old_id = element["id"]
            if (
                type(old_id) is not int
                or old_id == 0
                or (old_id < 0) != (action == "create")
            ):
                raise ValueError("Invalid road operation ID")
            if action != "create":
                _positive_id(element["version"], "Approved element version")
            key = (kind, old_id)
            if key in operations:
                raise ValueError("Repeated approved road operation")
            operations[key] = (action, element)
    return operations


def _road_mapping(
    operations: dict[ElementKey, tuple[str, Record]],
    diff: Sequence[Record],
    payload: Record,
) -> dict[ElementKey, int]:
    if (
        not operations
        or not isinstance(diff, (list, tuple))
        or len(diff) != len(operations)
    ):
        raise ValueError(
            "Road diff must contain exactly one row per approved operation"
        )

    # A new node may also not alias a positive reference that was only read
    # for this edit and consequently has no diffResult row of its own.
    existing = {key for key in operations if key[1] > 0}
    for kind in ("node", "way"):
        existing.update(
            (kind, int(key)) for key in payload.get(f"snapshot_{kind}s", {})
        )
    ways = [element for (kind, _), (_, element) in operations.items() if kind == "way"]
    ways.extend(payload.get("snapshot_ways", {}).values())
    for way in ways:
        for ref in way["node_ids"]:
            if (
                type(ref) is not int
                or ref == 0
                or (ref < 0 and ("node", ref) not in operations)
            ):
                raise ValueError("Unresolved node reference in approved road")
            if ref > 0:
                existing.add(("node", ref))

    mapping: dict[ElementKey, int] = {}
    allocated = set()
    for row in diff:
        if not isinstance(row, dict) or type(row.get("old_id")) is not int:
            raise ValueError("Malformed road diff mapping")
        key = (row["type"], row["old_id"])
        if key not in operations or key in mapping:
            raise ValueError("Unexpected or repeated road diff mapping")
        action, element = operations[key]
        new_id = _positive_id(row.get("new_id"), "Mapped element ID")
        version = row.get("new_version")
        if type(version) is not int:
            raise ValueError("Invalid mapped element version")
        if action == "create":
            assigned = (key[0], new_id)
            if version != 1 or assigned in allocated or assigned in existing:
                raise ValueError("Invalid or aliased created road element")
            allocated.add(assigned)
        elif new_id != key[1]:
            raise ValueError("Existing road element ID changed")
        elif action == "modify" and version != element["version"] + 1:
            raise ValueError("Modified way version differs from the approved operation")
        elif action == "delete" and version != 0 and version < element["version"]:
            raise ValueError("Invalid conditional node deletion version")
        mapping[key] = new_id
    return mapping


def _osm_coordinate(value: Any, limit: int) -> Decimal:
    # CGImap scales the uploaded double and rounds ties away from zero.
    value_scaled = float(_coordinate(value, limit)) * 10_000_000
    magnitude = abs(value_scaled)
    units = int(magnitude)
    if magnitude - units >= 0.5:
        units += 1
    return Decimal(-units if value_scaled < 0 else units).scaleb(-7)


def _verify_node(element: Any, expected: Record) -> None:
    for key, limit in (("lat", 90), ("lon", 180)):
        if _coordinate(element.get(key), limit) != _osm_coordinate(
            expected[key], limit
        ):
            raise ValueError("Node coordinates differ from the approved geometry")
    if _exact_tags(element) != expected.get("tags", {}):
        raise ValueError("Node tags differ from the approved tags")


def _verify_element(
    element: Any,
    action: str,
    expected: Record,
    row: Record,
    mapping: dict[ElementKey, int],
    changeset_id: int,
    version: int,
) -> str:
    if (
        element.tag != row["type"]
        or int(element.attrib["id"]) != row["new_id"]
        or int(element.attrib["version"]) != version
    ):
        raise ValueError("Readback element type, ID or version differs")
    changeset = _positive_id(int(element.attrib["changeset"]), "Readback changeset")
    visible = element.get("visible")
    if action == "delete" and row["new_version"] != 0:
        # if-unused returns the current ID and version when the deletion was
        # skipped, including when another changeset already deleted the node.
        if visible == "true" and version == expected["version"]:
            _verify_node(element, expected)
            return "skipped_visible"
        if (
            visible == "false"
            and version > expected["version"]
            and changeset != changeset_id
        ):
            return "skipped_already_deleted"
        raise ValueError("Readback does not establish a skipped conditional deletion")
    if changeset != changeset_id:
        raise ValueError("Readback version belongs to a different changeset")
    if action == "delete":
        if visible != "false":
            raise ValueError("Expected a deleted historical node")
        return "deleted"
    if visible != "true":
        raise ValueError("Expected a visible historical road element")
    if element.tag == "node":
        _verify_node(element, expected)
    else:
        refs = []
        tags = {}
        for child in element:
            if len(child):
                raise ValueError("Malformed way readback")
            if child.tag == "nd":
                refs.append(int(child.attrib["ref"]))
            elif child.tag == "tag" and child.attrib["k"] not in tags:
                tags[child.attrib["k"]] = child.attrib["v"]
            else:
                raise ValueError("Unexpected or duplicate way data")
        expected_refs = [
            mapping[("node", ref)] if ref < 0 else ref for ref in expected["node_ids"]
        ]
        if refs != expected_refs:
            raise ValueError("Way node references differ from the approved geometry")
        if tags != expected["tags"]:
            raise ValueError("Way tags differ from the approved tags")
    return "created" if action == "create" else "modified"


async def verify_road_upload(
    client: Any,
    diff_results: Sequence[Record],
    payload: Record,
    changeset_id: int,
) -> Record:
    """Prove the diff mapping and each uploaded version, even after later edits."""
    verified = []
    record: Record = {}
    try:
        _positive_id(changeset_id, "Changeset ID")
        operations = _road_operations(payload)
        mapping = _road_mapping(operations, diff_results, payload)
        for row in diff_results:
            kind, element_id = row["type"], row["new_id"]
            action, expected = operations[(kind, row["old_id"])]
            # An executed delete has no version attributes in the response;
            # the parser normalizes that shape to new_version zero.
            version = row["new_version"] or expected["version"] + 1
            record = {
                **row,
                "url": f"{config.current_web_base_url}/{kind}/{element_id}",
            }
            response = await client.get(
                f"{config.current_api_base_url}/{kind}/{element_id}/{version}"
            )
            if response.status_code != 200:
                raise ValueError(
                    f"Historical readback returned HTTP {response.status_code}"
                )
            root = parse_xml(response.text)
            if root.tag != "osm" or len(root) != 1:
                raise ValueError("Expected exactly one historical OSM element")
            outcome = _verify_element(
                root[0], action, expected, row, mapping, changeset_id, version
            )
            verified.append(
                {
                    **record,
                    "actual_version": version,
                    "outcome": outcome,
                    "verification_error": None,
                }
            )
    except Exception as exc:
        return {
            "status": "verification_incomplete",
            "verified": verified,
            "failures": [{**record, "verification_error": describe_exception(exc)}],
        }
    return {"status": "verified", "verified": verified, "failures": []}


async def verify_stored_road_upload(client: Any, proposal: StoredProposal) -> Record:
    """Recheck an existing receipt using its original proposal and changeset."""
    receipt = proposal.receipt or {}
    if (
        canonical_digest(proposal.payload, proposal.api_target, proposal.osm_uid)
        != proposal.digest
        or proposal.changeset_id is None
        or receipt.get("changeset_id") != proposal.changeset_id
    ):
        return {
            "status": "verification_incomplete",
            "verified": [],
            "failures": [
                {
                    "verification_error": "Road receipt does not match its proposal or changeset"
                }
            ],
        }
    return await verify_road_upload(
        client, receipt.get("diff_results", []), proposal.payload, proposal.changeset_id
    )
