"""Reviewed four-sided POI areas, optionally replacing one isolated POI node."""

import math
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Union

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt

from . import node_tools, track_tools
from .app import profile_tool
from .config import config
from .http_client import describe_exception
from .poi_duplicates import POLICY, _xy, geometry_distance, segments_intersect
from .proposal_store import canonical_digest

WAY_ID = -1_000_000
NODE_IDS = [-1, -2, -3, -4]
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True
)


class PolygonCorner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: Union[StrictFloat, StrictInt]
    longitude: Union[StrictFloat, StrictInt]


def _geometry(
    nodes: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, str], int]:
    if len(nodes) != 4:
        raise ValueError("Supply exactly four distinct corners in boundary order")
    points = [[float(n["lon"]), float(n["lat"])] for n in nodes]
    if len({tuple(p) for p in points}) != 4:
        raise ValueError(
            "Polygon needs four distinct corners; closure is added automatically"
        )
    if (
        any(abs(p[1]) > 85 for p in points)
        or max(p[0] for p in points) - min(p[0] for p in points) > 180
    ):
        raise ValueError(
            "Bounded POI polygons do not support polar or dateline-spanning geometry"
        )
    anchor = {
        "lat": str(sum(p[1] for p in points) / 4),
        "lon": str(sum(p[0] for p in points) / 4),
    }
    origin = (float(anchor["lat"]), float(anchor["lon"]))
    xy = [_xy(p, origin) for p in points]
    if any(math.dist(a, b) > 500 for a in xy for b in xy):
        raise ValueError("POI polygon diameter must not exceed 500 metres")
    if segments_intersect(
        points[0], points[1], points[2], points[3]
    ) or segments_intersect(points[1], points[2], points[3], points[0]):
        raise ValueError("Polygon boundary must not self-intersect or touch itself")
    for i in range(4):
        a, b, c = xy[i], xy[(i + 1) % 4], xy[(i + 2) % 4]
        if (
            math.dist(a, b) < 0.1
            or abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 0.01
        ):
            raise ValueError(
                "Polygon must have four nonzero sides and non-collinear corners"
            )
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1]))) / 2
    if area < 0.1:
        raise ValueError("Polygon area is degenerate")
    radius = math.ceil(node_tools.CONTEXT_RADIUS_M + max(math.hypot(*p) for p in xy))
    return {"type": "Polygon", "coordinates": [points + [points[0]]]}, anchor, radius


def validate_polygon_shape(
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    nodes, ways = payload.get("create_nodes"), payload.get("create_ways")
    if (
        payload.get("action") != "polygon_create"
        or payload.get("segment_id") is not None
        or payload.get("track_hash") is not None
    ):
        raise ValueError("Not a reviewed POI polygon proposal")
    if (
        not isinstance(nodes, list)
        or len(nodes) != 4
        or not isinstance(ways, list)
        or len(ways) != 1
    ):
        raise ValueError(
            "Polygon creation requires exactly four new vertices and one closed way"
        )
    if any(
        payload.get(key) for key in ("modify_nodes", "modify_ways", "snapshot_ways")
    ):
        raise ValueError("Polygon creation must not modify neighbouring OSM elements")
    for node, identifier in zip(nodes, NODE_IDS):
        if (
            set(node) != {"id", "lat", "lon", "tags"}
            or type(node["id"]) is not int
            or node["id"] != identifier
            or node["tags"] != {}
        ):
            raise ValueError("Polygon vertices must be four exact, untagged new nodes")
        node_tools._coordinate(node["lat"], 90, stored=True)
        node_tools._coordinate(node["lon"], 180, stored=True)
    way = ways[0]
    if (
        set(way) != {"id", "node_ids", "tags"}
        or type(way["id"]) is not int
        or way["id"] != WAY_ID
        or way["node_ids"] != NODE_IDS + [NODE_IDS[0]]
        or any(type(ref) is not int for ref in way["node_ids"])
    ):
        raise ValueError(
            "Way must close with the SAME first node reference and exactly four sides"
        )
    node_tools._validate_tags_and_metadata(
        way["tags"], payload.get("changeset_comment"), payload.get("changeset_source")
    )
    if way["tags"].get("area") == "no":
        raise ValueError("An area proposal cannot have area=no")
    demo = payload.get("demonstration")
    synthetic_source = any(
        word in payload["changeset_source"].casefold()
        for word in ("synthetic", "demonstration")
    )
    if (
        type(demo) is not bool
        or (demo or synthetic_source)
        and not config.is_development_api
    ):
        raise ValueError(
            "Synthetic demonstration polygons are allowed only on the official dev API"
        )
    if synthetic_source and not demo:
        raise ValueError(
            "Synthetic geometry requires demonstration=true and its explicit warning"
        )
    if demo and not synthetic_source:
        raise ValueError(
            "Demonstration evidence must explicitly identify synthetic geometry"
        )
    geometry, anchor, radius = _geometry(nodes)
    replacement = payload.get("replacement")
    if replacement is None:
        if payload.get("delete_nodes") or payload.get("snapshot_nodes"):
            raise ValueError(
                "No deletion is allowed without an explicit replacement source"
            )
    else:
        if not isinstance(replacement, dict) or set(replacement) != {
            "id",
            "version",
            "lat",
            "lon",
            "tags",
        }:
            raise ValueError("Replacement requires an exact inspected node snapshot")
        if (
            type(replacement["id"]) is not int
            or replacement["id"] <= 0
            or type(replacement["version"]) is not int
            or replacement["version"] <= 0
        ):
            raise ValueError(
                "Replacement ID and expected version must be positive integers"
            )
        node_tools._coordinate(replacement["lat"], 90, stored=True)
        node_tools._coordinate(replacement["lon"], 180, stored=True)
        if replacement["tags"] != way["tags"]:
            raise ValueError(
                "Replacement must preserve ALL original node tags on the polygon"
            )
        if (
            geometry_distance(
                geometry, (float(replacement["lat"]), float(replacement["lon"]))
            )
            != 0
        ):
            raise ValueError("Replacement node must lie within the reviewed polygon")
        if payload.get("delete_nodes") != [replacement] or payload.get(
            "snapshot_nodes"
        ) != {str(replacement["id"]): replacement}:
            raise ValueError(
                "Only the exact approved isolated POI node may be replaced"
            )
    return geometry, {**anchor, "tags": way["tags"], "geometry": geometry}, radius


async def _read_replacement(client: Any, identifier: int) -> Dict[str, Any]:
    response = await client.get(f"{config.current_api_base_url}/node/{identifier}")
    response.raise_for_status()
    root = parse_xml(response.text)
    if (
        root.tag != "osm"
        or len(root) != 1
        or root[0].tag != "node"
        or root[0].get("visible") != "true"
    ):
        raise ValueError("Replacement source must be one visible OSM node")
    element = root[0]
    result = {
        "id": node_tools._positive_int(element.attrib["id"]),
        "version": node_tools._positive_int(element.attrib["version"]),
        "lat": node_tools._coordinate(element.attrib["lat"], 90, from_api=True),
        "lon": node_tools._coordinate(element.attrib["lon"], 180, from_api=True),
        "tags": node_tools._read_tags(element),
    }
    if result["id"] != identifier:
        raise ValueError("Replacement response returned a different node")
    for suffix, kind in (("ways", "way"), ("relations", "relation")):
        response = await client.get(
            f"{config.current_api_base_url}/node/{identifier}/{suffix}"
        )
        response.raise_for_status()
        parents = parse_xml(response.text)
        if parents.tag != "osm" or any(
            child.tag not in {kind, "note", "meta"} for child in parents
        ):
            raise ValueError("Replacement parentage check is incomplete")
        if parents.findall(kind):
            raise ValueError(
                "Replacement node is used by a way or relation; preserve it and review manually"
            )
    return result


def _candidates(
    raw: List[Dict[str, Any]], payload: Dict[str, Any]
) -> List[Dict[str, Any]]:
    _, subject, _ = validate_polygon_shape(payload)
    source = payload.get("replacement")
    raw = [{k: v for k, v in item.items() if k != "replacement_source"} for item in raw]
    ordinary = [
        c
        for c in raw
        if source is None or (c["type"], c["id"]) != ("node", source["id"])
    ]
    decisions = payload.get("duplicate_decisions")
    reviewed = node_tools._review_candidates(ordinary, subject, decisions)
    if source is not None:
        matches = [c for c in raw if (c["type"], c["id"]) == ("node", source["id"])]
        if len(matches) != 1 or any(matches[0][key] != source[key] for key in source):
            raise ValueError(
                "Complete map search did not contain the exact replacement source"
            )
        candidate = node_tools._review_candidates(matches, subject)[0]
        candidate.update(blocking=False, replacement_source=True)
        candidate["reasons"].append(
            "Same POI explicitly replaced by this polygon; source node is removed in the same atomic upload"
        )
        reviewed.append(candidate)
    return sorted(
        reviewed, key=lambda c: (("node", "way", "relation").index(c["type"]), c["id"])
    )


def _check_search(payload: Dict[str, Any]) -> None:
    _, subject, radius = validate_polygon_shape(payload)
    search = payload.get("duplicate_search", {})
    if (
        search.get("status") != "completed"
        or search.get("completed") is not True
        or search.get("radius_m") != radius
        or search.get("policy") != POLICY
        or search.get("bboxes")
        != node_tools._context_bboxes(
            float(subject["lat"]), float(subject["lon"]), radius
        )
        or not isinstance(search.get("candidates"), list)
        or set(payload.get("context_snapshot", {})) != {"node", "way", "relation"}
    ):
        raise ValueError(
            "Polygon duplicate search is incomplete or changed; create a fresh preview"
        )
    if _candidates(search["candidates"], payload) != search["candidates"]:
        raise ValueError("Polygon duplicate classifications or decisions changed")


async def _recheck(client: Any, payload: Dict[str, Any]) -> None:
    _check_search(payload)
    source = payload.get("replacement")
    if source is not None and await _read_replacement(client, source["id"]) != source:
        raise ValueError(
            "Replacement node version, coordinates or tags changed; inspect again"
        )
    current = await node_tools._fetch_context(
        client, payload["duplicate_search"]["bboxes"]
    )
    if (
        current["snapshot"] != payload["context_snapshot"]
        or _candidates(current["candidates"], payload)
        != payload["duplicate_search"]["candidates"]
    ):
        raise ValueError(
            "Polygon map context changed; create a fresh proposal and repeat review"
        )


async def validate_polygon_context(client: Any, payload: Dict[str, Any]) -> None:
    _check_search(payload)
    if any(c["blocking"] for c in payload["duplicate_search"]["candidates"]):
        raise ValueError("Polygon has unresolved duplicate candidates")
    way_limit, server_limit = await track_tools._fetch_api_limits(client)
    if way_limit < 5 or min(config.max_changeset_size, server_limit) < 5 + bool(
        payload.get("replacement")
    ):
        raise ValueError("Polygon exceeds the API element or way-node limit")
    await _recheck(client, payload)


def _finish_payload(payload: Dict[str, Any], candidates: List[Dict[str, Any]]) -> None:
    payload["duplicate_search"]["candidates"] = candidates
    payload["duplicate_search"]["possible_duplicate_count"] = sum(
        c["classification"] != "context_only" and not c.get("replacement_source")
        for c in candidates
    )
    payload["duplicate_search"]["blocking_duplicate_count"] = sum(
        c["blocking"] for c in candidates
    )
    payload["blocking_issues"] = node_tools._blocking_issues(candidates)
    payload["blocking_issues"] = [
        issue.replace("review_node_create_duplicates", "review_poi_polygon_duplicates")
        for issue in payload["blocking_issues"]
    ]
    payload["summary"].update(
        duplicate_decisions=payload.get("duplicate_decisions"),
        blocking_duplicate_count=payload["duplicate_search"][
            "blocking_duplicate_count"
        ],
    )


def _result(proposal: track_tools.Proposal) -> Dict[str, Any]:
    p = proposal.payload
    features = [
        {
            "type": "Feature",
            "geometry": c["geometry"],
            "properties": {k: v for k, v in c.items() if k != "geometry"},
        }
        for c in p["duplicate_search"]["candidates"]
    ]
    result = track_tools._proposal_result(
        proposal,
        track_tools._feature_collection(features),
        track_tools._feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": p["summary"]["geometry"],
                    "properties": {
                        "review_state": "proposed",
                        "tags": p["create_ways"][0]["tags"],
                    },
                }
            ]
        ),
    )
    result["data"].update(
        duplicate_search=p["duplicate_search"],
        duplicate_decisions=p.get("duplicate_decisions"),
        revision=p["revision"],
        diff=p["diff"],
        replacement=p.get("replacement"),
        web_preview_url=None,
        web_preview_status="No web preview page is configured. preview_uri is an internal MCP HTML resource, not a web link.",
    )
    result["message"] = (
        "Four-sided POI polygon preview is ready for separate confirmation"
        if not p["blocking_issues"]
        else "Polygon preview has unresolved duplicates"
    )
    return result


@profile_tool(annotations=READ_ONLY)
async def preview_poi_polygon_create(
    corners: List[PolygonCorner],
    tags: Dict[str, str],
    changeset_comment: str,
    changeset_source: str,
    replace_node_id: Optional[StrictInt] = None,
    expected_node_version: Optional[StrictInt] = None,
    demonstration: bool = False,
) -> Dict[str, Any]:
    """Preview four ordered corners as a closed POI area, without uploading.

    Supply exactly four distinct latitude/longitude pairs at OSM precision.
    The server creates four untagged vertices and one closed way bearing all
    POI tags. No self-intersections, collinear corners, polar/dateline geometry
    or diameter over 500m. Searches the WHOLE polygon plus a 100m margin.
    Optional replace_node_id and expected_node_version explicitly replace one
    isolated, unchanged POI node inside the area, preserving all its tags on
    the new way and deleting it atomically. Parent ways/relations block this.
    demonstration=true permits synthetic geometry only on the official dev API;
    changeset_source must say synthetic or demonstration. Never infer a real
    boundary from one point. Review geometry, any deletion and the full digest;
    use apply_osm_edit with separate digest-bound host confirmation afterwards.
    """
    search: Dict[str, Any] = {"status": "unknown", "completed": False}
    try:
        parsed = [PolygonCorner.model_validate(c) for c in corners]
        nodes = [
            {
                "id": identifier,
                "lat": node_tools._coordinate(c.latitude, 90),
                "lon": node_tools._coordinate(c.longitude, 180),
                "tags": {},
            }
            for identifier, c in zip(NODE_IDS, parsed)
        ]
        if len(parsed) != 4:
            raise ValueError("Exactly four corners are required")
        if (
            (replace_node_id is None) != (expected_node_version is None)
            or replace_node_id is not None
            and (
                type(replace_node_id) is not int
                or replace_node_id <= 0
                or type(expected_node_version) is not int
                or expected_node_version <= 0
            )
        ):
            raise ValueError(
                "Replacement requires a positive node ID and its inspected version"
            )
        payload: Dict[str, Any] = {
            "action": "polygon_create",
            "segment_id": None,
            "track_hash": None,
            "changeset_comment": changeset_comment,
            "changeset_source": changeset_source,
            "demonstration": demonstration,
            "create_nodes": nodes,
            "create_ways": [
                {
                    "id": WAY_ID,
                    "node_ids": NODE_IDS + [NODE_IDS[0]],
                    "tags": dict(sorted(tags.items())),
                }
            ],
            "modify_nodes": [],
            "modify_ways": [],
            "delete_nodes": [],
            "snapshot_nodes": {},
            "snapshot_ways": {},
            "replacement": None,
            "duplicate_decisions": None,
            "revision": {"number": 1},
            "warnings": [],
            "blocking_issues": [],
        }
        geometry, subject, radius = validate_polygon_shape(payload)
        bboxes = node_tools._context_bboxes(
            float(subject["lat"]), float(subject["lon"]), radius
        )
        search.update(
            source="configured_osm_api_map",
            policy=deepcopy(POLICY),
            radius_m=radius,
            bboxes=bboxes,
            coverage="Whole reviewed polygon plus at least 100m margin",
            absence_proven=False,
            coverage_limitations=[
                "Enclosing areas with no vertex in the map bbox may be omitted; returned relation member geometry is conservative"
            ],
        )
        async with track_tools.get_authenticated_client() as client:
            identity = await track_tools.verify_write_identity(client)
            way_limit, server_limit = await track_tools._fetch_api_limits(client)
            if way_limit < 5 or min(config.max_changeset_size, server_limit) < 5 + (
                replace_node_id is not None
            ):
                raise ValueError("Polygon exceeds the API element or way-node limit")
            if replace_node_id is not None:
                source = await _read_replacement(client, replace_node_id)
                if source["version"] != expected_node_version:
                    raise ValueError("Replacement node changed since inspection")
                payload.update(
                    replacement=source,
                    delete_nodes=[source],
                    snapshot_nodes={str(replace_node_id): source},
                )
                validate_polygon_shape(payload)
            context = await node_tools._fetch_context(client, bboxes)
        search.update(
            status="completed", completed=True, element_count=context["element_count"]
        )
        payload.update(duplicate_search=search, context_snapshot=context["snapshot"])
        payload["warnings"] = [
            "Exact four-corner geometry must come from independent, permitted evidence.",
            "A bounded map search does not prove absence of all duplicates.",
        ]
        if demonstration:
            payload["warnings"].append(
                "SYNTHETIC DEMONSTRATION GEOMETRY ON DEV ONLY: this is not a surveyed real-world boundary."
            )
        if payload["replacement"]:
            payload["warnings"].append(
                "The inspected isolated node will be deleted in the same atomic upload; its tags move to the area."
            )
        payload["summary"] = {
            "geometry": geometry,
            "tags": payload["create_ways"][0]["tags"],
            "corners": [{"latitude": n["lat"], "longitude": n["lon"]} for n in nodes],
            "created_nodes": 4,
            "created_ways": 1,
            "sides": 4,
            "closed": True,
            "deleted_nodes": [replace_node_id] if replace_node_id else [],
            "replacement_node": payload["replacement"],
            "element_operations": 5 + (replace_node_id is not None),
            "demonstration": demonstration,
            "changeset_comment": changeset_comment,
            "changeset_source": changeset_source,
        }
        payload["diff"] = {
            "before": payload["replacement"],
            "after": {
                "way": payload["create_ways"][0],
                "vertices": nodes,
                "geometry": geometry,
            },
            "deleted_node": payload["replacement"],
        }
        _finish_payload(payload, _candidates(context["candidates"], payload))
        return _result(track_tools._store_proposal(payload, int(identity["user_id"])))
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Failed to preview POI polygon; no OSM write was sent",
            detail=describe_exception(exc),
            duplicate_search=search,
        )


@profile_tool(annotations=READ_ONLY)
async def review_poi_polygon_duplicates(
    proposal_id: str,
    proposal_digest: str,
    decisions: List[node_tools.DuplicateDecision],
) -> Dict[str, Any]:
    """Resolve every blocking polygon candidate in a new digest-bound revision.

    Same decisions and evidence requirements as review_node_create_duplicates.
    The explicitly replaced source node is reviewed as a conversion, never as
    a distinct object. Search, source version and parentage are rechecked.
    This stores a new preview only; separate final host approval is required.
    """
    try:
        stored = track_tools._PROPOSAL_STORE.get(proposal_id)
        if stored is None or stored.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
            raise ValueError("Unknown, expired or superseded polygon proposal")
        if (
            stored.digest != proposal_digest
            or canonical_digest(stored.payload, stored.api_target, stored.osm_uid)
            != proposal_digest
            or stored.api_target != config.current_api_base_url
        ):
            raise ValueError("Polygon digest or API target mismatch")
        payload = deepcopy(stored.payload)
        _check_search(payload)
        parsed = sorted(
            [
                node_tools.DuplicateDecision.model_validate(d).model_dump()
                for d in decisions
            ],
            key=lambda d: (d["osm_type"], d["osm_id"]),
        )
        payload["duplicate_decisions"] = parsed
        candidates = _candidates(payload["duplicate_search"]["candidates"], payload)
        async with track_tools.get_authenticated_client() as client:
            identity = await track_tools.verify_write_identity(client)
            if int(identity["user_id"]) != stored.osm_uid:
                raise ValueError("Polygon belongs to a different OSM account")
            await _recheck(client, stored.payload)
        payload.pop("_review", None)
        _finish_payload(payload, candidates)
        payload["revision"] = {
            "number": payload["revision"]["number"] + 1,
            "supersedes_proposal_id": stored.proposal_id,
            "supersedes_proposal_digest": stored.digest,
        }
        revision = track_tools._PROPOSAL_STORE.supersede_preview(
            stored.proposal_id,
            stored.digest,
            str(uuid.uuid4()),
            payload,
            stored.api_target,
            int(identity["user_id"]),
            config.osm_track_proposal_ttl_seconds,
        )
        track_tools._PROPOSALS.pop(proposal_id, None)
        proposal = track_tools._get_proposal(revision.proposal_id)
        assert proposal is not None
        return _result(proposal)
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Failed to review polygon duplicates; no OSM write was sent",
            detail=describe_exception(exc),
        )
