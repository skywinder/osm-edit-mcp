"""Reviewed creation of one POI node, with fail-closed map context checks."""

import math
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple, Union, cast

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import StrictFloat, StrictInt

from . import track_tools
from .app import profile_tool
from .config import config
from .http_client import describe_exception

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


def _contains_point(geometry: Dict[str, Any], point: Tuple[float, float]) -> bool:
    """Conservative polygon membership, including member areas of relations."""
    if geometry["type"] == "GeometryCollection":
        return any(_contains_point(member, point) for member in geometry["geometries"])
    if geometry["type"] != "Polygon":
        return False
    lat, lon = point
    # Put dateline-spanning polygon vertices on the same longitude branch.
    ring = [
        (lat_value, lon + ((lon_value - lon + 180) % 360 - 180))
        for lon_value, lat_value in geometry["coordinates"][0]
    ]
    if track_tools._nearest_on_polyline(point, ring)[0] < 0.01:
        return True
    inside = False
    for (lat_a, lon_a), (lat_b, lon_b) in zip(ring, ring[1:]):
        if (lat_a > lat) != (lat_b > lat) and lon < (
            (lon_b - lon_a) * (lat - lat_a) / (lat_b - lat_a) + lon_a
        ):
            inside = not inside
    return inside


def _review_candidates(
    candidates: List[Dict[str, Any]], node: Dict[str, Any]
) -> List[Dict[str, Any]]:
    proposed_families = {
        key
        for key, value in node["tags"].items()
        if key in POI_KEYS and value.casefold() not in UNSPECIFIED_CLASSIFICATIONS
    }
    point = (float(node["lat"]), float(node["lon"]))
    reviewed = []
    for candidate in candidates:
        tags = candidate["tags"]
        same_family = any(
            key in proposed_families and value.strip().casefold() not in ("no", "none")
            for key, value in tags.items()
        )
        containing_retail_area = (
            "shop" in proposed_families
            and tags.get("building") in ("retail", "supermarket")
            and _contains_point(candidate["geometry"], point)
        )
        reviewed.append(
            {
                **candidate,
                "potential_duplicate": same_family or containing_retail_area,
                "review_reason": (
                    "Same POI classification family"
                    if same_family
                    else (
                        "Retail area contains proposed point"
                        if containing_retail_area
                        else "Nearby POI of another classification; "
                        "review its geometry and tags"
                    )
                ),
            }
        )
    return reviewed


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


async def validate_node_create_context(client: Any, payload: Dict[str, Any]) -> None:
    """Reject altered node operations or uncertain/stale duplicate-search context."""
    node = _validate_node_create_shape(payload)
    search = payload.get("duplicate_search", {})
    bboxes = _context_bboxes(float(node["lat"]), float(node["lon"]))
    if (
        search.get("status") != "completed"
        or search.get("completed") is not True
        or search.get("radius_m") != CONTEXT_RADIUS_M
        or search.get("bboxes") != bboxes
        or not isinstance(search.get("candidates"), list)
        or not isinstance(payload.get("context_snapshot"), dict)
        or set(payload["context_snapshot"]) != {"node", "way", "relation"}
    ):
        raise ValueError(
            "Node-create duplicate search is incomplete or has unresolved nearby POIs"
        )
    if _review_candidates(search["candidates"], node) != search["candidates"] or any(
        candidate["potential_duplicate"] for candidate in search["candidates"]
    ):
        raise ValueError("Node-create duplicate search has unresolved nearby POIs")
    _, server_limit = await track_tools._fetch_api_limits(client)
    if min(config.max_changeset_size, server_limit) < 1:
        raise ValueError("Node creation exceeds changeset element limit")
    current = await _fetch_context(client, bboxes)
    candidates = _review_candidates(current["candidates"], node)
    if (
        current["snapshot"] != payload["context_snapshot"]
        or candidates != search["candidates"]
        or any(candidate["potential_duplicate"] for candidate in candidates)
    ):
        raise ValueError(
            "POI map context changed after preview; inspect it and "
            "create a fresh proposal"
        )


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
    100m; same-family POIs and retail areas containing the new shop block apply
    until fresh inspection
    resolves it. Failed or incomplete searches never establish absence.
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
            item for item in candidates if item["potential_duplicate"]
        ]
        search.update(
            {
                "status": "completed",
                "completed": True,
                "candidates": candidates,
                "element_count": context["element_count"],
                "possible_duplicate_count": len(possible_duplicates),
            }
        )
        blockers = (
            [
                "Nearby possible POI duplicates require inspection and a fresh "
                "preview; this proposal cannot be applied"
            ]
            if possible_duplicates
            else []
        )
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
        current = track_tools._feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": candidate["geometry"],
                    "properties": {
                        key: value
                        for key, value in candidate.items()
                        if key != "geometry"
                    },
                }
                for candidate in candidates
            ]
        )
        proposed = track_tools._feature_collection(
            [{"type": "Feature", "geometry": geometry, "properties": node}]
        )
        if len(candidates) > len(possible_duplicates):
            payload["warnings"].append(
                "Other nearby POIs are shown for review; their different "
                "classification does not establish that they are distinct businesses."
            )
        proposal = track_tools._store_proposal(payload, int(identity["user_id"]))
        result: Dict[str, Any] = track_tools._proposal_result(
            proposal, current, proposed
        )
        result["data"].update({"duplicate_search": search, "diff": payload["diff"]})
        result["message"] = (
            "Node-create preview contains possible duplicates and cannot be applied"
            if blockers
            else "Node-create preview is ready for explicit confirmation"
        )
        return result
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
