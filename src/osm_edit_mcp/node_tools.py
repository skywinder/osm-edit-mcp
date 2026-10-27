"""Reviewed creation of one POI node, with fail-closed map context checks."""

import math
import unicodedata
import uuid
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Literal, Tuple, Union, cast

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from . import track_tools
from .app import profile_tool
from .config import config
from .http_client import describe_exception
from .poi_duplicates import POLICY
from .poi_duplicates import review_candidates as _classify_candidates
from .proposal_store import canonical_digest

CONTEXT_RADIUS_M = 100.0
MAX_CONTEXT_ELEMENTS = 10_000
MAX_RELATION_FETCHES = 20
POI_KEYS = frozenset(
    ("shop", "amenity", "tourism", "leisure", "office", "craft", "healthcare")
)
NEARBY_POI_KEYS = POI_KEYS | frozenset(("historic", "emergency", "club"))
UNSPECIFIED_CLASSIFICATIONS = frozenset(("yes", "no", "none", "unknown", "fixme"))


def _text(text: Any) -> None:
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text.encode("utf-8")) > 255
        or any(unicodedata.category(char) == "Cc" for char in text)
    ):
        raise ValueError(
            "Tags and changeset metadata require nonempty text, at most 255 "
            "UTF-8 bytes, without control characters"
        )


def _coordinate(
    value: Any, limit: int, *, stored: bool = False, from_api: bool = False
) -> str:
    if stored or from_api:
        if not isinstance(value, str):
            raise ValueError("Stored node coordinates must be exact decimal strings")
    elif type(value) not in (int, float):
        raise ValueError("Coordinates must be numbers, not booleans or strings")
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Coordinates must be finite numbers") from exc
    if not decimal.is_finite() or not -limit <= decimal <= limit:
        raise ValueError("Coordinates must be finite and in range")
    rounded = decimal.quantize(Decimal("0.0000001"))
    if decimal != rounded:
        raise ValueError(
            "Coordinates must have at most seven decimal places; no rounding is applied"
        )
    # Avoid different encodings of the same zero in reviewed geometry.
    if rounded == 0:
        rounded = abs(rounded)
    normalized = format(rounded, ".7f")
    if stored and value != normalized:
        raise ValueError("Stored node coordinates are not canonical OSM decimals")
    return normalized


def _validate_tags_and_metadata(
    tags: Any, changeset_comment: Any, changeset_source: Any
) -> None:
    if not isinstance(tags, dict) or not 1 <= len(tags) <= 20:
        raise ValueError("tags must contain between 1 and 20 tags")
    for text in (changeset_comment, changeset_source, *tags.keys(), *tags.values()):
        _text(text)
    if any(value != value.strip() for key, value in tags.items() if key in POI_KEYS):
        raise ValueError(
            "POI classification values must not have surrounding whitespace"
        )
    if not any(
        key in POI_KEYS and value.casefold() not in UNSPECIFIED_CLASSIFICATIONS
        for key, value in tags.items()
    ):
        raise ValueError(
            "A new POI requires an explicit shop, amenity, tourism, leisure, "
            "office, craft or healthcare classification"
        )
    sources = [changeset_source] + [
        value
        for key, value in tags.items()
        if key == "source" or key.startswith("source:")
    ]
    if any(
        provider in source.casefold()
        for source in sources
        for provider in ("google", "yandex")
    ):
        raise ValueError("Restricted map providers are not permitted OSM evidence")


def _context_bboxes(lat: float, lon: float) -> List[str]:
    """Cover the survey point conservatively, including dateline/polar cases."""
    latitude_delta = CONTEXT_RADIUS_M / 110_000.0
    min_lat = max(-90.0, lat - latitude_delta)
    max_lat = min(90.0, lat + latitude_delta)
    cosine = abs(math.cos(math.radians(lat)))
    # A circle approaching a pole has a wider longitude span than a planar
    # latitude/cosine approximation. If it reaches a pole, search all meridians.
    longitude_delta = (
        180.0
        if min_lat == -90.0 or max_lat == 90.0
        else math.degrees(
            math.asin(min(1.0, math.sin(math.radians(latitude_delta)) / cosine))
        )
    )
    if longitude_delta == 180.0:
        intervals = [(-180.0, 180.0)]
    elif lon - longitude_delta < -180:
        intervals = [
            (-180.0, lon + longitude_delta),
            (lon - longitude_delta + 360, 180.0),
        ]
    elif lon + longitude_delta > 180:
        intervals = [
            (lon - longitude_delta, 180.0),
            (-180.0, lon + longitude_delta - 360),
        ]
    else:
        intervals = [(lon - longitude_delta, lon + longitude_delta)]
    boxes = []
    # /map limits a request to 0.25 square degrees. Keep polar requests bounded.
    max_width = min(180.0, 0.24 / (max_lat - min_lat))
    for left, right in intervals:
        count = max(1, math.ceil((right - left) / max_width))
        for index in range(count):
            a = left + (right - left) * index / count
            b = left + (right - left) * (index + 1) / count
            boxes.append(f"{a:.10f},{min_lat:.10f},{b:.10f},{max_lat:.10f}")
    return sorted(boxes)


def _read_tags(element: Any) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for child in element.findall("tag"):
        key, value = child.attrib["k"], child.attrib["v"]
        # Upstream OSM uses a Unicode-character limit. Keep all valid remote
        # names for review, including Arabic names exceeding 255 UTF-8 bytes.
        for text in (key, value):
            if (
                not text.strip()
                or len(text) > 255
                or any(unicodedata.category(char) == "Cc" for char in text)
            ):
                raise ValueError("OSM map tags contain invalid text")
        if key in tags:
            raise ValueError("Duplicate tag keys in OSM map data")
        tags[key] = value
    return dict(sorted(tags.items()))


def _positive_int(value: Any) -> int:
    parsed = int(value)
    if str(parsed) != str(value) or parsed <= 0:
        raise ValueError("OSM context contains an invalid element ID or version")
    return parsed


def _merge_document(xml: str, records: Dict[str, Dict[int, Dict[str, Any]]]) -> None:
    root = parse_xml(xml)
    if root.tag != "osm":
        raise ValueError("Duplicate search response is not an OSM map document")
    if root.find("error") is not None or root.find("remark") is not None:
        raise ValueError("Duplicate search response reports incomplete map data")
    for element in root:
        kind = element.tag
        if kind in ("bounds", "note", "meta"):
            continue
        if kind not in records or element.get("visible") == "false":
            raise ValueError("Duplicate search contains invalid or invisible map data")
        record: Dict[str, Any] = {
            "type": kind,
            "id": _positive_int(element.attrib["id"]),
            "version": _positive_int(element.attrib["version"]),
            "tags": _read_tags(element),
        }
        if kind == "node":
            # Canonical precision permits semantically equal API decimal formatting.
            record["lat"] = _coordinate(element.attrib["lat"], 90, from_api=True)
            record["lon"] = _coordinate(element.attrib["lon"], 180, from_api=True)
        elif kind == "way":
            record["node_ids"] = [
                _positive_int(child.attrib["ref"]) for child in element.findall("nd")
            ]
            if len(record["node_ids"]) < 2:
                raise ValueError("Duplicate search contains an incomplete way")
        else:
            members = []
            for child in element.findall("member"):
                if child.attrib["type"] not in records:
                    raise ValueError(
                        "Duplicate search contains an invalid relation member"
                    )
                members.append(
                    {
                        "type": child.attrib["type"],
                        "ref": _positive_int(child.attrib["ref"]),
                        "role": child.get("role", ""),
                    }
                )
            record["members"] = members
        previous = records[kind].get(record["id"])
        if previous is not None and previous != record:
            raise ValueError(
                "OSM map context changed while duplicate search was running"
            )
        records[kind][record["id"]] = record
        if sum(len(items) for items in records.values()) > MAX_CONTEXT_ELEMENTS:
            raise ValueError("Duplicate search exceeds the complete-map element limit")


def _is_poi(record: Dict[str, Any]) -> bool:
    tags = record["tags"]
    return any(
        key in NEARBY_POI_KEYS and value.casefold() not in ("no", "none")
        for key, value in tags.items()
    ) or tags.get("building") in ("retail", "supermarket", "commercial")


def _geometry(
    kind: str,
    identifier: int,
    records: Dict[str, Dict[int, Dict[str, Any]]],
    ancestors: Tuple[int, ...] = (),
) -> Dict[str, Any]:
    record = records[kind].get(identifier)
    if record is None:
        raise ValueError("Duplicate search is missing referenced POI geometry")
    if kind == "node":
        return {
            "type": "Point",
            "coordinates": [float(record["lon"]), float(record["lat"])],
        }
    if kind == "way":
        coordinates = [
            _geometry("node", ref, records)["coordinates"] for ref in record["node_ids"]
        ]
        closed = (
            len(coordinates) >= 4 and record["node_ids"][0] == record["node_ids"][-1]
        )
        return {
            "type": (
                "Polygon"
                if closed and record["tags"].get("area") != "no"
                else "LineString"
            ),
            "coordinates": (
                [coordinates]
                if closed and record["tags"].get("area") != "no"
                else coordinates
            ),
        }
    if identifier in ancestors or len(ancestors) >= MAX_RELATION_FETCHES:
        raise ValueError(
            "Duplicate search contains cyclic or excessively nested POI geometry"
        )
    if not record["members"]:
        raise ValueError("Duplicate search contains a POI relation without geometry")
    return {
        "type": "GeometryCollection",
        "geometries": [
            _geometry(member["type"], member["ref"], records, (*ancestors, identifier))
            for member in record["members"]
        ],
    }


def _node_in_bboxes(node: Dict[str, Any], bboxes: List[str]) -> bool:
    lat, lon = float(node["lat"]), float(node["lon"])
    return any(
        left <= lon <= right and bottom <= lat <= top
        for left, bottom, right, top in (map(float, box.split(",")) for box in bboxes)
    )


class DuplicateDecision(BaseModel):
    """An evidence-backed decision about one exact candidate version."""

    model_config = ConfigDict(extra="forbid")
    osm_type: Literal["node", "way", "relation"]
    osm_id: StrictInt = Field(gt=0)
    expected_version: StrictInt = Field(gt=0)
    decision: Literal["distinct_object", "same_object", "uncertain"]
    reason: str
    evidence_source: str


def _review_candidates(
    candidates: List[Dict[str, Any]],
    node: Dict[str, Any],
    decisions: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    # Strip derived annotations before reclassification so validation can detect
    # stale or altered signals and review decisions.
    derived = {
        "classification",
        "reasons",
        "blocking",
        "distance_m",
        "osm_url",
        "review_decision",
    }
    raw = [
        {key: value for key, value in item.items() if key not in derived}
        for item in candidates
    ]
    reviewed = _classify_candidates(raw, node)
    by_id = {(item["type"], item["id"]): item for item in reviewed}
    decision_map = {}
    for value in decisions or []:
        decision = DuplicateDecision.model_validate(value).model_dump()
        for text in (decision["reason"], decision["evidence_source"]):
            _text(text)
        _validate_evidence_source(decision["evidence_source"])
        key = (decision["osm_type"], decision["osm_id"])
        if key in decision_map or key not in by_id:
            raise ValueError(
                "Decision must identify one unique candidate in the proposal"
            )
        candidate = by_id[key]
        if candidate["version"] != decision["expected_version"]:
            raise ValueError(
                "Decision expected_version does not match the candidate version"
            )
        decision_map[key] = decision
    if decisions is not None and any(
        candidate["blocking"] and key not in decision_map
        for key, candidate in by_id.items()
    ):
        raise ValueError("A decision is required for every blocking candidate")
    for key, candidate in by_id.items():
        candidate["osm_url"] = f"{config.current_web_base_url}/{key[0]}/{key[1]}"
        if key in decision_map:
            decision = decision_map[key]
            candidate["review_decision"] = decision
            candidate["blocking"] = decision["decision"] != "distinct_object"
    return reviewed


def _validate_evidence_source(source: str) -> None:
    if any(provider in source.casefold() for provider in ("google", "yandex")):
        raise ValueError("Restricted map providers are not permitted OSM evidence")


async def _fetch_context(client: Any, bboxes: List[str]) -> Dict[str, Any]:
    records: Dict[str, Dict[int, Dict[str, Any]]] = {
        "node": {},
        "way": {},
        "relation": {},
    }
    for bbox in bboxes:
        response = await client.get(
            f"{config.current_api_base_url}/map", params={"bbox": bbox}
        )
        response.raise_for_status()
        _merge_document(response.text, records)
    original_ids = {kind: set(items) for kind, items in records.items()}
    poi_relations = [
        identifier
        for identifier, relation in records["relation"].items()
        if _is_poi(relation)
    ]
    fetched: set[int] = set()

    async def complete_relation(
        identifier: int, ancestors: Tuple[int, ...] = ()
    ) -> None:
        if identifier in ancestors or len(ancestors) >= MAX_RELATION_FETCHES:
            raise ValueError("Duplicate search contains cyclic POI relation geometry")
        relation = records["relation"].get(identifier)
        missing = relation is None or any(
            member["ref"] not in records[member["type"]]
            for member in relation["members"]
        )
        if missing:
            if identifier in fetched or len(fetched) >= MAX_RELATION_FETCHES:
                raise ValueError(
                    "Duplicate search cannot complete POI relation geometry"
                )
            fetched.add(identifier)
            response = await client.get(
                f"{config.current_api_base_url}/relation/{identifier}/full"
            )
            response.raise_for_status()
            _merge_document(response.text, records)
            relation = records["relation"].get(identifier)
            if relation is None:
                raise ValueError(
                    "Duplicate search full response omitted the POI relation"
                )
        if relation is None:
            raise ValueError("Duplicate search omitted the referenced POI relation")
        for member in relation["members"]:
            if member["type"] == "relation":
                await complete_relation(member["ref"], (*ancestors, identifier))

    for identifier in sorted(poi_relations):
        await complete_relation(identifier)
    # /map promises complete ways. A missing node is uncertainty, not no POIs.
    for way in records["way"].values():
        if any(ref not in records["node"] for ref in way["node_ids"]):
            raise ValueError(
                "Duplicate search map response contains incomplete way geometry"
            )
    candidates = []
    for kind in ("node", "way", "relation"):
        for identifier in sorted(original_ids[kind]):
            record = records[kind][identifier]
            if not _is_poi(record) or (
                kind == "node" and not _node_in_bboxes(record, bboxes)
            ):
                continue
            candidates.append(
                {**record, "geometry": _geometry(kind, identifier, records)}
            )
    return {
        "snapshot": {
            kind: [records[kind][identifier] for identifier in sorted(records[kind])]
            for kind in ("node", "way", "relation")
        },
        "candidates": candidates,
        "element_count": sum(len(items) for items in records.values()),
    }


def _validate_node_create_shape(payload: Dict[str, Any]) -> Dict[str, Any]:
    nodes = payload.get("create_nodes")
    if (
        payload.get("action") != "node_create"
        or payload.get("segment_id") is not None
        or payload.get("track_hash") is not None
        or not isinstance(nodes, list)
        or len(nodes) != 1
        or any(
            payload.get(key)
            for key in (
                "create_ways",
                "modify_ways",
                "modify_nodes",
                "delete_nodes",
                "snapshot_nodes",
                "snapshot_ways",
            )
        )
    ):
        raise ValueError("Node-create proposal must create exactly one POI node")
    node = nodes[0]
    if (
        not isinstance(node, dict)
        or set(node) != {"id", "lat", "lon", "tags"}
        or type(node["id"]) is not int
        or node["id"] != -1
    ):
        raise ValueError(
            "Node-create proposal requires exactly the reviewed temporary node -1"
        )
    _coordinate(node["lat"], 90, stored=True)
    _coordinate(node["lon"], 180, stored=True)
    _validate_tags_and_metadata(
        node["tags"], payload.get("changeset_comment"), payload.get("changeset_source")
    )
    return node


def _checked_search(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    node = _validate_node_create_shape(payload)
    search = payload.get("duplicate_search", {})
    bboxes = _context_bboxes(float(node["lat"]), float(node["lon"]))
    if (
        search.get("status") != "completed"
        or search.get("completed") is not True
        or search.get("radius_m") != CONTEXT_RADIUS_M
        or search.get("bboxes") != bboxes
        or search.get("policy") != POLICY
        or not isinstance(search.get("candidates"), list)
        or not isinstance(payload.get("context_snapshot"), dict)
        or set(payload["context_snapshot"]) != {"node", "way", "relation"}
    ):
        raise ValueError(
            "Node-create duplicate search is incomplete or stale; create a fresh preview"
        )
    candidates = _review_candidates(
        search["candidates"], node, payload.get("duplicate_decisions")
    )
    if candidates != search["candidates"]:
        raise ValueError(
            "Stored duplicate classifications or decisions changed; create a fresh preview"
        )
    return node, bboxes


async def _recheck_context(client: Any, payload: Dict[str, Any]) -> None:
    node, bboxes = _checked_search(payload)
    current = await _fetch_context(client, bboxes)
    candidates = _review_candidates(
        current["candidates"], node, payload.get("duplicate_decisions")
    )
    if (
        current["snapshot"] != payload["context_snapshot"]
        or candidates != payload["duplicate_search"]["candidates"]
    ):
        raise ValueError(
            "POI map context or candidate version changed after preview; create a fresh proposal and repeat duplicate review"
        )


async def validate_node_create_context(client: Any, payload: Dict[str, Any]) -> None:
    """Require a complete, freshly unchanged search and resolved candidates."""
    _checked_search(payload)
    if any(
        candidate["blocking"] for candidate in payload["duplicate_search"]["candidates"]
    ):
        raise ValueError("Node-create duplicate search has unresolved nearby POIs")
    _, server_limit = await track_tools._fetch_api_limits(client)
    if min(config.max_changeset_size, server_limit) < 1:
        raise ValueError("Node creation exceeds changeset element limit")
    await _recheck_context(client, payload)


def _blocking_issues(candidates: List[Dict[str, Any]]) -> List[str]:
    blockers = [item for item in candidates if item["blocking"]]
    if not blockers:
        return []
    issues = [
        "Nearby possible POI duplicates require review_node_create_duplicates before applying"
    ]
    if any(
        item.get("review_decision", {}).get("decision") == "same_object"
        for item in blockers
    ):
        issues.append(
            "An existing candidate is the same object; edit the existing OSM object instead of creating a node"
        )
    return issues


def _node_create_result(proposal: track_tools.Proposal) -> Dict[str, Any]:
    payload = proposal.payload
    candidates = payload["duplicate_search"]["candidates"]
    current = track_tools._feature_collection(
        [
            {
                "type": "Feature",
                "geometry": candidate["geometry"],
                "properties": {
                    key: value for key, value in candidate.items() if key != "geometry"
                },
            }
            for candidate in candidates
        ]
    )
    proposed = track_tools._feature_collection(
        [
            {
                "type": "Feature",
                "geometry": payload["summary"]["geometry"],
                "properties": {
                    **payload["create_nodes"][0],
                    "review_state": "proposed",
                },
            }
        ]
    )
    result: Dict[str, Any] = track_tools._proposal_result(proposal, current, proposed)
    result["data"].update(
        {
            "duplicate_search": payload["duplicate_search"],
            "duplicate_decisions": payload.get("duplicate_decisions"),
            "revision": payload["revision"],
            "diff": payload["diff"],
            "web_preview_url": None,
            "web_preview_status": "No web preview page is configured. preview_uri is an internal MCP HTML resource, not a web link.",
        }
    )
    result["message"] = (
        "Node-create preview contains unresolved duplicates and cannot be applied"
        if payload["blocking_issues"]
        else "Node-create preview is ready for separate explicit confirmation"
    )
    return result


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
async def preview_node_create(
    latitude: Union[StrictFloat, StrictInt],
    longitude: Union[StrictFloat, StrictInt],
    tags: Dict[str, str],
    changeset_comment: str,
    changeset_source: str,
) -> Dict[str, Any]:
    """Preview one new POI without writing to OSM.

    Coordinates must be finite, in range and exact at OSM's seven decimal
    places. Supply 1..20 nonempty string tags including an explicit POI
    classification and the actual independent evidence source. Requires
    verified OAuth/write_api. Searches the configured OSM API within about
    100m; classifies nearby geometry by explicit POI type, sport, distance
    and identity signals. Blocking candidates need review_node_create_duplicates.
    That tool creates a new digest; it never uploads or approves a write.
    Failed or incomplete searches never establish absence.
    Review the exact geometry, tags, diff and full SHA-256 digest before a
    later apply_osm_edit and separate genuine MCP-host user elicitation.
    """
    search: Dict[str, Any] = {"status": "unknown", "completed": False}
    try:
        lat, lon = _coordinate(latitude, 90), _coordinate(longitude, 180)
        _validate_tags_and_metadata(tags, changeset_comment, changeset_source)
        node = {"id": -1, "lat": lat, "lon": lon, "tags": dict(sorted(tags.items()))}
        geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}
        bboxes = _context_bboxes(float(lat), float(lon))
        search.update(
            {
                "source": "configured_osm_api_map",
                "policy": deepcopy(POLICY),
                "radius_m": CONTEXT_RADIUS_M,
                "bboxes": bboxes,
                "coverage": "Bounded OSM map query and returned POI relations",
                "absence_proven": False,
                "coverage_limitations": [
                    "Enclosing areas whose vertices all lie outside the bbox "
                    "may be omitted by the OSM map API"
                ],
            }
        )
        async with track_tools.get_authenticated_client() as client:
            identity = await track_tools.verify_write_identity(client)
            _, server_limit = await track_tools._fetch_api_limits(client)
            if min(config.max_changeset_size, server_limit) < 1:
                raise ValueError("Node creation exceeds changeset element limit")
            context = await _fetch_context(client, bboxes)
        candidates = _review_candidates(context["candidates"], node)
        possible_duplicates = [
            item for item in candidates if item["classification"] != "context_only"
        ]
        search.update(
            {
                "status": "completed",
                "completed": True,
                "candidates": candidates,
                "element_count": context["element_count"],
                "possible_duplicate_count": len(possible_duplicates),
                "blocking_duplicate_count": sum(
                    item["blocking"] for item in candidates
                ),
            }
        )
        blockers = _blocking_issues(candidates)
        payload = {
            "action": "node_create",
            "segment_id": None,
            "track_hash": None,
            "changeset_comment": changeset_comment,
            "changeset_source": changeset_source,
            "create_nodes": [node],
            "create_ways": [],
            "modify_ways": [],
            "modify_nodes": [],
            "delete_nodes": [],
            "snapshot_nodes": {},
            "snapshot_ways": {},
            "duplicate_search": search,
            "duplicate_decisions": None,
            "revision": {"number": 1},
            "context_snapshot": context["snapshot"],
            "diff": {"before": None, "after": node},
            "warnings": [
                "No name, opening hours or other operating-information tags "
                "should be inferred from proprietary maps.",
                "A completed bounded search does not guarantee absence of an "
                "unmapped or differently tagged duplicate.",
                "The OSM map API can omit enclosing POI areas whose vertices "
                "all fall outside the search bbox; review independent on-site "
                "evidence before confirming creation.",
            ],
            "blocking_issues": blockers,
            "summary": {
                "created_nodes": 1,
                "element_operations": 1,
                "geometry": geometry,
                "latitude": lat,
                "longitude": lon,
                "tags": node["tags"],
                "changeset_comment": changeset_comment,
                "changeset_source": changeset_source,
                "possible_duplicate_count": len(possible_duplicates),
            },
        }
        if len(candidates) > len(possible_duplicates):
            payload["warnings"].append(
                "Other nearby POIs are shown for review; their different "
                "classification does not establish that they are distinct businesses."
            )
        proposal = track_tools._store_proposal(payload, int(identity["user_id"]))
        return _node_create_result(proposal)
    except Exception as exc:
        return cast(
            Dict[str, Any],
            track_tools._failure(
                type(exc).__name__,
                "Failed to preview node creation; no OSM write was sent",
                detail=describe_exception(exc),
                duplicate_search=search,
            ),
        )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
async def review_node_create_duplicates(
    proposal_id: str,
    proposal_digest: str,
    decisions: List[DuplicateDecision],
) -> Dict[str, Any]:
    """Review every blocking candidate and return a new node-create revision.

    Decisions bind exact candidate type, ID and expected_version. Every decision
    requires a reason and independent evidence_source. distinct_object resolves
    that match; same_object requires editing the existing object; uncertain
    stays blocked. Unknown candidates, omitted blockers and changed versions
    are rejected. This only stores a preview: review the new complete digest,
    then obtain separate user confirmation through apply_osm_edit. No OSM write
    or user approval occurs here. Superseded proposals cannot be applied.
    """
    try:
        stored = track_tools._PROPOSAL_STORE.get(proposal_id)
        if stored is None or stored.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
            raise ValueError(
                "Unknown, expired or superseded proposal; create a fresh preview"
            )
        if (
            stored.digest != proposal_digest
            or canonical_digest(stored.payload, stored.api_target, stored.osm_uid)
            != proposal_digest
        ):
            raise ValueError("Proposal digest mismatch")
        if stored.api_target != config.current_api_base_url:
            raise ValueError("Proposal belongs to a different API target")
        payload = deepcopy(stored.payload)
        node, _ = _checked_search(payload)
        parsed = [
            DuplicateDecision.model_validate(item).model_dump() for item in decisions
        ]
        parsed.sort(key=lambda item: (item["osm_type"], item["osm_id"]))
        candidates = _review_candidates(
            payload["duplicate_search"]["candidates"], node, parsed
        )
        async with track_tools.get_authenticated_client() as client:
            identity = await track_tools.verify_write_identity(client)
            if int(identity["user_id"]) != stored.osm_uid:
                raise ValueError("Proposal belongs to a different OSM account")
            await _recheck_context(client, stored.payload)
        payload.pop("_review", None)
        payload["duplicate_decisions"] = parsed
        search = payload["duplicate_search"]
        search["candidates"] = candidates
        search["blocking_duplicate_count"] = sum(
            item["blocking"] for item in candidates
        )
        payload["blocking_issues"] = _blocking_issues(candidates)
        payload["revision"] = {
            "number": payload["revision"]["number"] + 1,
            "supersedes_proposal_id": stored.proposal_id,
            "supersedes_proposal_digest": stored.digest,
        }
        payload["summary"]["duplicate_decisions"] = parsed
        payload["summary"]["blocking_duplicate_count"] = search[
            "blocking_duplicate_count"
        ]
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
        return _node_create_result(proposal)
    except Exception as exc:
        return cast(
            Dict[str, Any],
            track_tools._failure(
                type(exc).__name__,
                "Failed to review node-create duplicates; no OSM write was sent",
                detail=describe_exception(exc),
            ),
        )
