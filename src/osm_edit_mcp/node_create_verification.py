"""Strict read-only verification and recovery for a single new POI node.

Recovery is only evidence gathering: an empty or unavailable changeset is never
permission to retry an upload. Callers must supply the dedicated changeset they
created for this proposal after checking the authenticated account identity.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Sequence

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config
from .http_client import describe_exception


def _coordinate(value: Any, limit: int) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Node coordinates must be numeric")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Node coordinates must be numeric") from exc
    if not number.is_finite() or not -limit <= number <= limit:
        raise ValueError("Node coordinates are outside the valid range")
    return number


def _expected_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    nodes = payload.get("create_nodes")
    if (
        not isinstance(nodes, list)
        or len(nodes) != 1
        or any(
            payload.get(key)
            for key in ("create_ways", "modify_nodes", "modify_ways", "delete_nodes")
        )
    ):
        raise ValueError("Node creation must contain exactly one create-node operation")
    node = nodes[0]
    if (
        not isinstance(node, dict)
        or type(node.get("id")) is not int
        or node["id"] != -1
    ):
        raise ValueError("The approved new node must have temporary ID -1")
    tags = node.get("tags")
    if (
        not isinstance(tags, dict)
        or not tags
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in tags.items()
        )
    ):
        raise ValueError("Approved node tags must be a nonempty string mapping")
    for key, limit in (("lat", 90), ("lon", 180)):
        coordinate = _coordinate(node.get(key), limit)
        if coordinate != coordinate.quantize(Decimal("0.0000001")):
            raise ValueError(
                "Approved coordinates must be normalized to seven decimals"
            )
    return node


def _positive_id(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _exact_tags(element: Any) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for child in element:
        if child.tag != "tag" or len(child):
            raise ValueError("Created node contains unexpected XML children")
        key, value = child.get("k"), child.get("v")
        if key is None or value is None or key in tags:
            raise ValueError(
                "Created node contains missing or duplicate tag attributes"
            )
        tags[key] = value
    return tags


def _validate_node(
    element: Any,
    expected: Dict[str, Any],
    node_id: int,
    changeset_id: int,
    *,
    require_visible: bool,
) -> None:
    if element.tag != "node":
        raise ValueError("OSM response does not contain the expected node")
    if (
        int(element.get("id", "0")) != node_id
        or int(element.get("version", "0")) != 1
        or int(element.get("changeset", "0")) != changeset_id
    ):
        raise ValueError(
            "Created node ID, version or changeset differs from the receipt"
        )
    visible = element.get("visible")
    if visible != "true" and (require_visible or visible is not None):
        raise ValueError("Created node visibility could not be verified")
    if (
        _coordinate(element.get("lat"), 90) != _coordinate(expected["lat"], 90)
        or _coordinate(element.get("lon"), 180) != _coordinate(expected["lon"], 180)
        or _exact_tags(element) != expected["tags"]
    ):
        raise ValueError(
            "Created node coordinates or complete tags differ from the proposal"
        )


def _incomplete(error: str, record: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "status": "verification_incomplete",
        "verified": [],
        "failures": [{**(record or {}), "verification_error": error}],
    }


async def verify_node_create(
    client: Any,
    diff_results: Sequence[Dict[str, Any]],
    payload: Dict[str, Any],
    changeset_id: int,
) -> Dict[str, Any]:
    """Prove the one approved create mapping and its complete OSM readback."""
    try:
        expected = _expected_node(payload)
        changeset_id = _positive_id(changeset_id, "Changeset ID")
        if not isinstance(diff_results, (list, tuple)) or len(diff_results) != 1:
            raise ValueError("Upload diff must contain exactly one created node")
        item = diff_results[0]
        if (
            not isinstance(item, dict)
            or item.get("type") != "node"
            or type(item.get("old_id")) is not int
            or item["old_id"] != -1
            or type(item.get("new_version")) is not int
            or item["new_version"] != 1
        ):
            raise ValueError(
                "Upload diff does not match the approved new-node operation"
            )
        node_id = _positive_id(item.get("new_id"), "Created node ID")
    except Exception as exc:
        return _incomplete(describe_exception(exc))

    record = {
        **item,
        "url": f"{config.current_web_base_url}/node/{node_id}",
        "actual_version": None,
        "verification_error": None,
    }
    try:
        response = await client.get(f"{config.current_api_base_url}/node/{node_id}")
        if response.status_code != 200:
            raise ValueError(
                f"Created node readback failed with HTTP {response.status_code}"
            )
        root = parse_xml(response.text)
        if root.tag != "osm" or len(root) != 1 or root[0].tag != "node":
            raise ValueError(
                "Node readback must contain exactly one node in an osm root"
            )
        element = root[0]
        record["actual_version"] = int(element.get("version", "0"))
        _validate_node(element, expected, node_id, changeset_id, require_visible=True)
    except Exception as exc:
        return _incomplete(describe_exception(exc), record)
    return {"status": "verified", "verified": [record], "failures": []}


async def reconcile_node_create(
    client: Any, payload: Dict[str, Any], changeset_id: int
) -> Dict[str, Any]:
    """Resolve an uncertain create only with exact download and readback evidence."""
    try:
        expected = _expected_node(payload)
        changeset_id = _positive_id(changeset_id, "Changeset ID")
        response = await client.get(
            f"{config.current_api_base_url}/changeset/{changeset_id}/download"
        )
        if response.status_code != 200:
            raise ValueError(
                f"Changeset download failed with HTTP {response.status_code}"
            )
        root = parse_xml(response.text)
        if (
            root.tag != "osmChange"
            or len(root) != 1
            or root[0].tag != "create"
            or len(root[0]) != 1
            or root[0][0].tag != "node"
        ):
            raise ValueError("Changeset download must contain exactly one create/node")
        element = root[0][0]
        node_id = int(element.get("id", "0"))
        _positive_id(node_id, "Created node ID")
        _validate_node(element, expected, node_id, changeset_id, require_visible=False)
        diff_results: List[Dict[str, Any]] = [
            {"type": "node", "old_id": -1, "new_id": node_id, "new_version": 1}
        ]
        verification = await verify_node_create(
            client, diff_results, payload, changeset_id
        )
        if verification["status"] != "verified":
            return {
                "status": "unresolved",
                "error": (
                    "Changeset matches, but the created node could not be verified"
                ),
                "verification": verification,
            }
        return {
            "status": "reconciled",
            "diff_results": diff_results,
            "verification": verification,
        }
    except Exception as exc:
        return {"status": "unresolved", "error": describe_exception(exc)}


__all__ = ["verify_node_create", "reconcile_node_create"]
