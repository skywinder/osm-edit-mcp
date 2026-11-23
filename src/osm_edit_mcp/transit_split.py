"""Preview and check a way split at existing road nodes for a bus route."""

from typing import Annotated, Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import Field

from . import track_tools
from .app import profile_tool
from .auth import verify_write_identity
from .config import config
from .http_client import describe_exception, get_authenticated_client
from .node_tools import _text as validate_osm_text
from .transit_apply import read_route_parents
from .transit_data import element_tags, fetch_route_objects
from .transit_geometry import BUS_ROADS

Record = dict[str, Any]
ObjectId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
MAX_CUTS = 40
# These describe a junction, a transition, a whole feature/measurement or its
# endpoint. Duplicating them across every segment could change their meaning.
SEGMENT_TAGS = {
    "junction",
    "change",
    "turn",
    "destination",
    "placement",
    "traffic_sign",
    "direction",
    "incline",
    "distance",
    "length",
    "duration",
    "ascent",
    "descent",
    "start",
    "end",
    "from",
    "to",
    "wikidata",
    "wikipedia",
    "connectivity",
}


def _operations(way: Record, cuts: list[int]) -> tuple[list[Record], list[Record]]:
    refs, tags = way["nodes"], way["tags"]
    if (
        tags.get("highway") not in BUS_ROADS
        or tags.get("area") == "yes"
        or len(set(refs)) != len(refs)
    ):
        raise ValueError("A split needs a simple open road without repeated nodes")
    sensitive = sorted(k for k in tags if SEGMENT_TAGS.intersection(k.split(":")))
    if sensitive:
        raise ValueError(
            f"Segment-specific tags require manual split review: {sensitive}"
        )
    if (
        not 1 <= len(cuts) <= MAX_CUTS
        or len(set(cuts)) != len(cuts)
        or not set(cuts).issubset(refs[1:-1])
    ):
        raise ValueError("Provide distinct existing interior nodes for every split")
    if (
        way["id"] <= 0
        or way["version"] <= 0
        or any(type(ref) is not int or ref <= 0 for ref in refs)
    ):
        raise ValueError(
            "Existing way and node references must have positive OSM IDs and versions"
        )
    selected = set(cuts)
    bounds = [0, *(i for i, ref in enumerate(refs) if ref in selected), len(refs) - 1]
    parts = [
        {"id": -i, "tags": tags, "node_ids": refs[a : b + 1]}
        for i, (a, b) in enumerate(zip(bounds, bounds[1:]))
    ]
    # Retain the original orientation in each part; forward/backward access and
    # oneway tags continue to refer to the same direction after splitting.
    return [{**parts[0], "id": way["id"], "version": way["version"]}], parts[1:]


async def _plan(
    client: Any, way_id: int, cuts: list[int]
) -> tuple[Record, dict[int, Record]]:
    ways, nodes = await fetch_route_objects(client, [way_id], [])
    way = ways[way_id]
    modify, create = _operations(way, cuts)
    parents = await read_route_parents(client, [{"type": "way", "ref": way_id}])
    if parents:
        raise ValueError(
            f"Way {way_id} belongs to relations {sorted(parents)}. Split it in a relation-aware editor and reselect the route ways"
        )
    max_nodes, max_changes = await track_tools._fetch_api_limits(client)
    if 1 + len(create) > min(max_changes, config.max_changeset_size) or any(
        len(w["node_ids"]) > max_nodes for w in modify + create
    ):
        raise ValueError(
            "The approved pieces would exceed the OSM element or way node limit"
        )
    return {
        "split_way_id": way_id,
        "split_node_ids": [w["node_ids"][0] for w in create],
        "modify_ways": modify,
        "create_ways": create,
        "create_nodes": [],
        "modify_nodes": [],
        "delete_nodes": [],
        "snapshot_ways": {
            str(way_id): {
                "version": way["version"],
                "tags": way["tags"],
                "node_ids": way["nodes"],
            }
        },
        "snapshot_nodes": {
            str(ref): {"version": n["version"]} for ref, n in nodes.items()
        },
    }, nodes


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=True
    )
)
async def preview_bus_way_split(
    way_id: ObjectId,
    split_node_ids: Annotated[list[ObjectId], Field(min_length=1, max_length=MAX_CUTS)],
    source: Annotated[str, Field(min_length=1, max_length=255)],
) -> Record:
    """Review splitting a parentless road at mapped interior nodes of a surveyed bus route.

    Uses the existing points, orientation and road tags. The first piece retains
    the way ID. Review the pieces and apply the independent proposal with
    apply_osm_edit, then use the returned positive way IDs to preview the route.
    """
    try:
        validate_osm_text(source)
        source = source.strip()
        if any(
            type(ref) is not int or not 0 < ref < 2**63
            for ref in [way_id, *split_node_ids]
        ):
            raise ValueError("Positive OSM way and node IDs are required")
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
            uid = int(identity["user_id"])
            if uid <= 0:
                raise ValueError("A positive verified OSM user ID is required")
            plan, nodes = await _plan(client, way_id, split_node_ids)
        pieces = plan["modify_ways"] + plan["create_ways"]
        payload = {
            **plan,
            "action": "bus_way_split",
            "split_osm_uid": uid,
            "track_hash": None,
            "segment_id": None,
            "changeset_source": source,
            "changeset_comment": f"Split road {way_id} at bus route connection or terminus",
            "warnings": [],
            "blocking_issues": [],
            "summary": {
                "way_id": way_id,
                "split_node_ids": plan["split_node_ids"],
                "new_nodes": 0,
                "modified_ways": 1,
                "new_ways": len(pieces) - 1,
                "element_operations": len(pieces),
            },
        }

        def feature(refs: list[int], identifier: int) -> Record:
            return track_tools._line_feature(
                [(nodes[n]["lat"], nodes[n]["lon"]) for n in refs],
                {"way_id": identifier},
            )

        current = track_tools._feature_collection(
            [feature(plan["snapshot_ways"][str(way_id)]["node_ids"], way_id)]
        )
        proposed = track_tools._feature_collection(
            [feature(w["node_ids"], w["id"]) for w in pieces]
        )
        proposal = track_tools._store_proposal(payload, uid)
        result = track_tools._proposal_result(proposal, current, proposed)
        result["message"] = (
            "Review the road split before applying. Use its verified way IDs in a fresh route preview."
        )
        return result
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Could not preview this bus-route road split",
            detail=describe_exception(exc),
        )


async def validate_split_context(client: Any, payload: Record) -> None:
    if (
        payload.get("action") != "bus_way_split"
        or type(payload.get("split_osm_uid")) is not int
        or payload["split_osm_uid"] <= 0
    ):
        raise ValueError("Invalid road split proposal")
    plan, _ = await _plan(client, payload["split_way_id"], payload["split_node_ids"])
    if any(payload.get(k) != v for k, v in plan.items()):
        raise ValueError("The road, its nodes or its split plan changed since preview")


def _read_diff(payload: Record, diff: list[Record]) -> list[tuple[Record, Record]]:
    pieces = payload["modify_ways"] + payload["create_ways"]
    expected = {w["id"]: w for w in pieces}
    if len(diff) != len(expected):
        raise ValueError("Incomplete or unexpected operations in the split diff")
    actual_ids = set()
    matched = {}
    for row in diff:
        old, new, version = row.get("old_id"), row.get("new_id"), row.get("new_version")
        way = expected.get(old)
        if (
            row.get("type") != "way"
            or not way
            or type(old) is not int
            or type(new) is not int
            or type(version) is not int
            or new <= 0
            or new in actual_ids
            or old in matched
            or (old > 0 and new != old)
            or version != way.get("version", 0) + 1
        ):
            raise ValueError(
                "Split diff IDs or versions differ from the approved operations"
            )
        actual_ids.add(new)
        matched[old] = row
    return [(piece, matched[piece["id"]]) for piece in pieces]


def _check_way(
    element: Element, expected: Record, row: Record, changeset_id: int, uid: int
) -> None:
    if (
        element.tag != "way"
        or element.get("visible") == "false"
        or int(element.get("id", "0")) != row["new_id"]
        or int(element.get("version", "0")) != row["new_version"]
        or int(element.get("changeset", "0")) != changeset_id
        or int(element.get("uid", "0")) != uid
        or [int(n.attrib["ref"]) for n in element.findall("nd")] != expected["node_ids"]
        or element_tags(element) != expected["tags"]
        or len(element.findall("tag")) != len(expected["tags"])
        or any(n.tag not in {"nd", "tag"} for n in element)
    ):
        raise ValueError(
            f"Readback for way {row['new_id']} differs from the approved split, owner or changeset"
        )


async def verify_split_diff(
    client: Any, payload: Record, diff_results: list[Record], changeset_id: int
) -> Record:
    verified = []
    try:
        for way, row in _read_diff(payload, diff_results):
            ref = row["new_id"]
            response = await client.get(f"{config.current_api_base_url}/way/{ref}")
            response.raise_for_status()
            root = parse_xml(response.text)
            if root.tag != "osm" or len(root) != 1:
                raise ValueError("Expected one OSM way in the split readback")
            _check_way(root[0], way, row, changeset_id, payload["split_osm_uid"])
            verified.append({**row, "url": f"{config.current_web_base_url}/way/{ref}"})
    except Exception as exc:
        return {
            "status": "verification_incomplete",
            "verified": verified,
            "failures": [{"verification_error": describe_exception(exc)}],
        }
    return {"status": "verified", "verified": verified, "failures": []}


def split_diff_from_download(
    xml: str | bytes, payload: Record, changeset_id: int
) -> list[Record]:
    """Reconstruct temporary-ID mappings by exact ordered nodes of each piece."""
    root = parse_xml(xml)
    if root.tag != "osmChange":
        raise ValueError("Expected changeset download XML")
    pieces = {
        tuple(w["node_ids"]): w for w in payload["modify_ways"] + payload["create_ways"]
    }
    rows = []
    for section in root:
        if section.tag not in {"create", "modify"}:
            raise ValueError("Unexpected section in split changeset")
        for element in section:
            shape = tuple(int(n.attrib["ref"]) for n in element.findall("nd"))
            piece = pieces.get(shape)
            if not piece or section.tag != ("create" if piece["id"] < 0 else "modify"):
                raise ValueError("Unexpected operation in split changeset")
            row = {
                "type": "way",
                "old_id": piece["id"],
                "new_id": int(element.attrib["id"]),
                "new_version": int(element.attrib["version"]),
            }
            _check_way(element, piece, row, changeset_id, payload["split_osm_uid"])
            rows.append(row)
    return [row for _, row in _read_diff(payload, rows)]
