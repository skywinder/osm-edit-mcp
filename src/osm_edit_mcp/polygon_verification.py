"""Exact readback and read-only recovery of one four-sided POI upload."""

from typing import Any, Dict, List, Sequence

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config
from .http_client import describe_exception
from .node_create_verification import _coordinate, _positive_id, _validate_node
from .polygon_tools import WAY_ID, validate_polygon_shape


def _mapping(
    payload: Dict[str, Any], diff: Sequence[Dict[str, Any]]
) -> Dict[tuple[str, int], int]:
    validate_polygon_shape(payload)
    expected = {("node", node["id"]) for node in payload["create_nodes"]} | {
        ("way", WAY_ID)
    }
    source = payload.get("replacement")
    if not isinstance(diff, (list, tuple)) or len(diff) != 5 + bool(source):
        raise ValueError(
            "Polygon upload must map exactly four new nodes, one way and the optional source deletion"
        )
    result = {}
    seen = set()
    for item in diff:
        if not isinstance(item, dict) or type(item.get("old_id")) is not int:
            raise ValueError("Invalid polygon upload mapping")
        key = (item.get("type"), item["old_id"])
        if key in seen:
            raise ValueError("Repeated polygon upload mapping")
        seen.add(key)
        if source and key == ("node", source["id"]):
            if (
                item.get("new_id") != source["id"]
                or type(item.get("new_version")) is not int
                or item["new_version"] not in (0, source["version"] + 1)
            ):
                raise ValueError("Unexpected source deletion mapping")
            continue
        if (
            key not in expected
            or type(item.get("new_version")) is not int
            or item["new_version"] != 1
        ):
            raise ValueError("Polygon diff contains an unapproved operation or version")
        result[key] = _positive_id(item.get("new_id"), "Created polygon element ID")
    if (
        set(result) != expected
        or len({result[key] for key in result if key[0] == "node"}) != 4
    ):
        raise ValueError("Missing or aliased polygon vertices")
    if source and source["id"] in [result[key] for key in result if key[0] == "node"]:
        raise ValueError("A new vertex cannot alias the replaced node")
    return result


def _way(
    element: Any,
    payload: Dict[str, Any],
    mapping: Dict[tuple[str, int], int],
    changeset_id: int,
) -> None:
    if (
        element.tag != "way"
        or int(element.get("id", "0")) != mapping[("way", WAY_ID)]
        or int(element.get("version", "0")) != 1
        or int(element.get("changeset", "0")) != changeset_id
        or element.get("visible") not in (None, "true")
    ):
        raise ValueError(
            "Created way identity, version, visibility or changeset differs"
        )
    refs = []
    tags = {}
    for child in element:
        if len(child):
            raise ValueError("Malformed polygon way children")
        if child.tag == "nd":
            refs.append(int(child.attrib["ref"]))
        elif (
            child.tag == "tag"
            and child.get("k") is not None
            and child.get("v") is not None
            and child.get("k") not in tags
        ):
            tags[child.attrib["k"]] = child.attrib["v"]
        else:
            raise ValueError("Unexpected or duplicate polygon way children")
    expected = [mapping[("node", ref)] for ref in payload["create_ways"][0]["node_ids"]]
    if refs != expected or tags != payload["create_ways"][0]["tags"]:
        raise ValueError(
            "Created way closure, ordered corners or complete tags differ from the proposal"
        )


def _deleted(
    element: Any, source: Dict[str, Any], changeset_id: int, *, require_visible: bool
) -> None:
    if (
        element.tag != "node"
        or int(element.get("id", "0")) != source["id"]
        or int(element.get("version", "0")) != source["version"] + 1
        or int(element.get("changeset", "0")) != changeset_id
    ):
        raise ValueError("Replacement deletion identity, version or changeset differs")
    if element.get("visible") != "false" and (
        require_visible or element.get("visible") is not None
    ):
        raise ValueError("Original POI node was not verified as deleted")


async def verify_polygon_create(
    client: Any,
    diff_results: Sequence[Dict[str, Any]],
    payload: Dict[str, Any],
    changeset_id: int,
) -> Dict[str, Any]:
    try:
        changeset_id = _positive_id(changeset_id, "Changeset ID")
        mapping = _mapping(payload, diff_results)
        way_id = mapping[("way", WAY_ID)]
        response = await client.get(f"{config.current_api_base_url}/way/{way_id}/full")
        response.raise_for_status()
        root = parse_xml(response.text)
        if root.tag != "osm" or len(root) != 5:
            raise ValueError(
                "Polygon readback must contain exactly one way and four nodes"
            )
        elements = {}
        for element in root:
            key = (element.tag, int(element.get("id", "0")))
            if key in elements:
                raise ValueError("Repeated element in polygon readback")
            elements[key] = element
        if set(elements) != {(kind, new_id) for (kind, _), new_id in mapping.items()}:
            raise ValueError("Polygon readback has missing or unexpected elements")
        way = elements[("way", way_id)]
        if way.get("visible") != "true":
            raise ValueError("Polygon way visibility is unknown")
        _way(way, payload, mapping, changeset_id)
        for node in payload["create_nodes"]:
            node_id = mapping[("node", node["id"])]
            _validate_node(
                elements[("node", node_id)],
                node,
                node_id,
                changeset_id,
                require_visible=True,
            )
        source = payload.get("replacement")
        if source:
            response = await client.get(
                f"{config.current_api_base_url}/node/{source['id']}/history"
            )
            response.raise_for_status()
            history = parse_xml(response.text)
            if (
                history.tag != "osm"
                or not len(history)
                or any(
                    e.tag != "node" or int(e.get("id", "0")) != source["id"]
                    for e in history
                )
            ):
                raise ValueError("Replacement deletion history is incomplete")
            latest = max(history, key=lambda e: int(e.get("version", "0")))
            _deleted(latest, source, changeset_id, require_visible=True)
        return {
            "status": "verified",
            "way_id": way_id,
            "way_url": f"{config.current_web_base_url}/way/{way_id}",
            "corner_node_ids": [
                mapping[("node", n["id"])] for n in payload["create_nodes"]
            ],
            "sides": 4,
            "closed": True,
            "replaced_node_id": source["id"] if source else None,
            "verified": list(diff_results),
            "failures": [],
        }
    except Exception as exc:
        return {
            "status": "verification_incomplete",
            "verified": [],
            "failures": [{"verification_error": describe_exception(exc)}],
        }


async def reconcile_polygon_create(
    client: Any, payload: Dict[str, Any], changeset_id: int
) -> Dict[str, Any]:
    """Recover exact mappings only; never upload, delete or retry anything."""
    try:
        validate_polygon_shape(payload)
        response = await client.get(
            f"{config.current_api_base_url}/changeset/{changeset_id}/download"
        )
        response.raise_for_status()
        root = parse_xml(response.text)
        if root.tag != "osmChange":
            raise ValueError("Not a polygon changeset download")
        created: List[Any] = []
        deleted: List[Any] = []
        for section in root:
            if section.tag not in {"create", "delete"} or not len(section):
                raise ValueError("Changeset contains unapproved operations")
            (created if section.tag == "create" else deleted).extend(section)
        nodes = [e for e in created if e.tag == "node"]
        ways = [e for e in created if e.tag == "way"]
        source = payload.get("replacement")
        if (
            len(created) != 5
            or len(nodes) != 4
            or len(ways) != 1
            or len(deleted) != bool(source)
        ):
            raise ValueError(
                "Changeset must contain exactly the approved polygon and optional source deletion"
            )
        mapping = {}
        diff: List[Dict[str, Any]] = []
        for expected in payload["create_nodes"]:
            matches = [
                e
                for e in nodes
                if _coordinate(e.get("lat"), 90) == _coordinate(expected["lat"], 90)
                and _coordinate(e.get("lon"), 180) == _coordinate(expected["lon"], 180)
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Polygon corner cannot be mapped uniquely from the changeset"
                )
            element = matches[0]
            identifier = _positive_id(int(element.get("id", "0")), "Corner node ID")
            _validate_node(
                element, expected, identifier, changeset_id, require_visible=False
            )
            mapping[("node", expected["id"])] = identifier
            diff.append(
                {
                    "type": "node",
                    "old_id": expected["id"],
                    "new_id": identifier,
                    "new_version": 1,
                }
            )
        way_id = _positive_id(int(ways[0].get("id", "0")), "Way ID")
        mapping[("way", WAY_ID)] = way_id
        _way(ways[0], payload, mapping, changeset_id)
        diff.append(
            {"type": "way", "old_id": WAY_ID, "new_id": way_id, "new_version": 1}
        )
        if source:
            _deleted(deleted[0], source, changeset_id, require_visible=False)
            diff.append(
                {
                    "type": "node",
                    "old_id": source["id"],
                    "new_id": source["id"],
                    "new_version": 0,
                }
            )
        verification = await verify_polygon_create(client, diff, payload, changeset_id)
        if verification["status"] != "verified":
            raise ValueError(
                f"Changeset matches, but polygon readback failed: {verification['failures']}"
            )
        return {
            "status": "reconciled",
            "diff_results": diff,
            "verification": verification,
        }
    except Exception as exc:
        return {"status": "unresolved", "error": describe_exception(exc)}
