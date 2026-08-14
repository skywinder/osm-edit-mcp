"""Safe GPX-to-OSM road editing tools.

The public workflow is deliberately two phase: callers inspect/suggest/preview,
then explicitly apply an unexpired proposal.  Geometry writes use one
``osmChange`` upload so new nodes, way changes, and cleanup are transactional.
"""

import asyncio
import hashlib
import math
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from defusedxml.ElementTree import fromstring as parse_xml

from .app import mcp
from .config import config
from .http_client import (
    describe_exception,
    get_authenticated_client,
    get_public_client,
)
from .token_store import load_oauth_token
from .write_tools import close_changeset, create_changeset


Point = Tuple[float, float]  # (lat, lon)
MAX_WAY_NODES_FALLBACK = 2_000
MAX_CHANGESET_ELEMENTS_FALLBACK = 10_000
DEFAULT_SIMPLIFY_TOLERANCE_M = 3.0
DEFAULT_ENDPOINT_SNAP_M = 10.0
DEFAULT_MAX_ALIGNMENT_M = 20.0
MAX_SURVEY_POINT_GAP_M = 500.0


@dataclass(frozen=True)
class TrackSegment:
    segment_id: str
    name: str
    points: Tuple[Point, ...]
    times: Tuple[Optional[str], ...]


@dataclass
class Proposal:
    proposal_id: str
    created_at: float
    expires_at: float
    payload: Dict[str, Any]


_PROPOSALS: Dict[str, Proposal] = {}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _failure(error: str, message: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": False,
        "error": error,
        "message": message,
    }
    result.update(extra)
    return result


def _read_track_source(
    gpx_xml: Optional[str], gpx_path: Optional[str]
) -> Tuple[str, str]:
    if (gpx_xml is None) == (gpx_path is None):
        raise ValueError("Provide exactly one of gpx_xml or gpx_path")

    if gpx_xml is not None:
        encoded = gpx_xml.encode("utf-8")
        if len(encoded) > config.osm_track_max_file_bytes:
            raise ValueError(
                f"GPX input exceeds {config.osm_track_max_file_bytes} bytes"
            )
        return gpx_xml, "inline"

    import_root = Path(config.osm_track_import_dir).expanduser().resolve()
    requested = Path(str(gpx_path)).expanduser()
    if not requested.is_absolute():
        requested = import_root / requested
    resolved = requested.resolve()
    try:
        resolved.relative_to(import_root)
    except ValueError as exc:
        raise ValueError(
            f"GPX path must stay inside configured import directory {import_root}"
        ) from exc
    if resolved.suffix.lower() != ".gpx":
        raise ValueError("Track file must use the .gpx extension")
    if not resolved.is_file():
        raise ValueError(f"GPX file does not exist: {resolved}")
    size = resolved.stat().st_size
    if size > config.osm_track_max_file_bytes:
        raise ValueError(f"GPX file exceeds {config.osm_track_max_file_bytes} bytes")
    return resolved.read_text(encoding="utf-8"), str(resolved)


def _parse_gpx(xml_text: str) -> Tuple[str, List[TrackSegment]]:
    root = parse_xml(xml_text)
    if _local_name(root.tag).lower() != "gpx":
        raise ValueError("Input root element is not <gpx>")

    segments: List[TrackSegment] = []
    total_points = 0
    track_index = -1
    for child in root:
        if _local_name(child.tag) != "trk":
            continue
        track_index += 1
        name = next(
            (
                (item.text or "").strip()
                for item in child
                if _local_name(item.tag) == "name"
            ),
            "",
        )
        segment_index = -1
        for segment in child:
            if _local_name(segment.tag) != "trkseg":
                continue
            segment_index += 1
            points: List[Point] = []
            times: List[Optional[str]] = []
            for element in segment:
                if _local_name(element.tag) != "trkpt":
                    continue
                total_points += 1
                if total_points > config.osm_track_max_points:
                    raise ValueError(
                        f"GPX exceeds {config.osm_track_max_points} track points"
                    )
                lat_text = element.get("lat")
                lon_text = element.get("lon")
                if lat_text is None or lon_text is None:
                    raise ValueError("Every GPX track point must have lat and lon")
                try:
                    lat, lon = float(lat_text), float(lon_text)
                except ValueError as exc:
                    raise ValueError("GPX contains a non-numeric coordinate") from exc
                if not math.isfinite(lat) or not math.isfinite(lon):
                    raise ValueError("GPX coordinates must be finite")
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError(f"Invalid GPX coordinate: {lat}, {lon}")
                timestamp = next(
                    (
                        (item.text or "").strip() or None
                        for item in element
                        if _local_name(item.tag) == "time"
                    ),
                    None,
                )
                point = (lat, lon)
                if not points or point != points[-1]:
                    points.append(point)
                    times.append(timestamp)
            if points:
                segments.append(
                    TrackSegment(
                        segment_id=f"trk-{track_index}-seg-{segment_index}",
                        name=name,
                        points=tuple(points),
                        times=tuple(times),
                    )
                )

    if not segments:
        raise ValueError("GPX contains no track segments with track points")
    digest = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
    return digest, segments


def _load_track(
    gpx_xml: Optional[str], gpx_path: Optional[str]
) -> Tuple[str, str, List[TrackSegment]]:
    xml_text, source = _read_track_source(gpx_xml, gpx_path)
    digest, segments = _parse_gpx(xml_text)
    return digest, source, segments


def _select_segment(segments: Sequence[TrackSegment], segment_id: str) -> TrackSegment:
    for segment in segments:
        if segment.segment_id == segment_id:
            if len(segment.points) < 2:
                raise ValueError("Selected segment must contain at least two points")
            return segment
    available = ", ".join(segment.segment_id for segment in segments)
    raise ValueError(f"Unknown segment_id {segment_id!r}; available: {available}")


def _haversine_m(a: Point, b: Point) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6_371_008.8 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _length_m(points: Sequence[Point]) -> float:
    return sum(_haversine_m(a, b) for a, b in zip(points, points[1:]))


def _segment_discontinuities(segment: TrackSegment) -> List[Dict[str, Any]]:
    """Return implausible jumps that must be cropped out before road editing."""
    result = []
    for point_index, (start, end) in enumerate(
        zip(segment.points, segment.points[1:]), start=1
    ):
        distance = _haversine_m(start, end)
        if distance > MAX_SURVEY_POINT_GAP_M:
            result.append(
                {
                    "before_point_index": point_index - 1,
                    "after_point_index": point_index,
                    "distance_m": round(distance, 2),
                }
            )
    return result


def _require_continuous_segment(segment: TrackSegment) -> None:
    discontinuities = _segment_discontinuities(segment)
    if discontinuities:
        largest = max(item["distance_m"] for item in discontinuities)
        raise ValueError(
            f"Selected segment contains {len(discontinuities)} discontinuous GPS "
            f"jump(s), largest {largest:.1f}m. Crop or split the specific surveyed "
            "path into a continuous GPX segment before suggesting or previewing an edit."
        )


def _bounds(points: Sequence[Point]) -> Dict[str, float]:
    return {
        "min_lat": min(point[0] for point in points),
        "min_lon": min(point[1] for point in points),
        "max_lat": max(point[0] for point in points),
        "max_lon": max(point[1] for point in points),
    }


def _xy_m(point: Point, origin: Point) -> Tuple[float, float]:
    lat, lon = point
    origin_lat, origin_lon = origin
    y = math.radians(lat - origin_lat) * 6_371_008.8
    x = (
        math.radians(lon - origin_lon)
        * 6_371_008.8
        * math.cos(math.radians((lat + origin_lat) / 2))
    )
    return x, y


def _point_segment_projection(
    point: Point, start: Point, end: Point
) -> Tuple[float, float, Point]:
    origin = point
    sx, sy = _xy_m(start, origin)
    ex, ey = _xy_m(end, origin)
    dx, dy = ex - sx, ey - sy
    denominator = dx * dx + dy * dy
    t = 0.0 if denominator == 0 else -(sx * dx + sy * dy) / denominator
    t = max(0.0, min(1.0, t))
    px, py = sx + t * dx, sy + t * dy
    projected = (
        start[0] + t * (end[0] - start[0]),
        start[1] + t * (end[1] - start[1]),
    )
    return math.hypot(px, py), t, projected


def _nearest_on_polyline(
    point: Point, line: Sequence[Point]
) -> Tuple[float, int, float, Point, float]:
    if len(line) < 2:
        raise ValueError("Polyline must contain at least two points")
    lengths = [_haversine_m(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths) or 1.0
    best: Optional[Tuple[float, int, float, Point, float]] = None
    travelled = 0.0
    for index, (start, end, length) in enumerate(zip(line, line[1:], lengths)):
        distance, t, projected = _point_segment_projection(point, start, end)
        fraction = (travelled + t * length) / total
        candidate = (distance, index, t, projected, fraction)
        if best is None or candidate[0] < best[0]:
            best = candidate
        travelled += length
    assert best is not None
    return best


def _perpendicular_distance(point: Point, start: Point, end: Point) -> float:
    return _point_segment_projection(point, start, end)[0]


def _simplify(points: Sequence[Point], tolerance_m: float) -> List[Point]:
    if len(points) <= 2 or tolerance_m <= 0:
        return list(points)
    max_distance = -1.0
    split_index = 0
    for index in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[index], points[0], points[-1])
        if distance > max_distance:
            max_distance, split_index = distance, index
    if max_distance > tolerance_m:
        left = _simplify(points[: split_index + 1], tolerance_m)
        right = _simplify(points[split_index:], tolerance_m)
        return left[:-1] + right
    return [points[0], points[-1]]


def _interpolate_line(line: Sequence[Point], fraction: float) -> Point:
    fraction = max(0.0, min(1.0, fraction))
    lengths = [_haversine_m(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths)
    if total == 0:
        return line[0]
    target = fraction * total
    travelled = 0.0
    for start, end, length in zip(line, line[1:], lengths):
        if travelled + length >= target:
            t = 0.0 if length == 0 else (target - travelled) / length
            return (
                start[0] + t * (end[0] - start[0]),
                start[1] + t * (end[1] - start[1]),
            )
        travelled += length
    return line[-1]


def _slice_line(line: Sequence[Point], start: float, end: float) -> List[Point]:
    if end < start:
        start, end = end, start
    result = [_interpolate_line(line, start)]
    cumulative = 0.0
    lengths = [_haversine_m(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths) or 1.0
    for point, length in zip(line[1:], lengths):
        cumulative += length
        fraction = cumulative / total
        if start < fraction < end:
            result.append(point)
    result.append(_interpolate_line(line, end))
    return result


def _line_feature(
    points: Sequence[Point], properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for lat, lon in points],
        },
    }


def _feature_collection(features: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def _expanded_bbox(points: Sequence[Point], radius_m: float) -> Tuple[float, ...]:
    bounds = _bounds(points)
    middle_lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
    lat_delta = radius_m / 111_320.0
    lon_scale = max(0.01, math.cos(math.radians(middle_lat)))
    lon_delta = radius_m / (111_320.0 * lon_scale)
    return (
        bounds["min_lat"] - lat_delta,
        bounds["min_lon"] - lon_delta,
        bounds["max_lat"] + lat_delta,
        bounds["max_lon"] + lon_delta,
    )


async def _nearby_highways(
    points: Sequence[Point], radius_m: float
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    south, west, north, east = _expanded_bbox(points, radius_m)
    # /map is part of the configured Editing API, so development previews do
    # not accidentally suggest production Overpass IDs. Keep each tile well
    # below the API's usual 0.25 square-degree area limit.
    max_span = 0.2
    lat_steps = max(1, math.ceil((north - south) / max_span))
    lon_steps = max(1, math.ceil((east - west) / max_span))
    if lat_steps * lon_steps > 100:
        raise ValueError("Track bounds require more than 100 OSM map tiles")
    boxes = []
    for lat_index in range(lat_steps):
        tile_south = south + (north - south) * lat_index / lat_steps
        tile_north = south + (north - south) * (lat_index + 1) / lat_steps
        for lon_index in range(lon_steps):
            tile_west = west + (east - west) * lon_index / lon_steps
            tile_east = west + (east - west) * (lon_index + 1) / lon_steps
            boxes.append((tile_west, tile_south, tile_east, tile_north))

    xml_documents: List[str] = []
    async with get_public_client() as client:
        responses = await asyncio.gather(
            *(
                client.get(
                    f"{config.current_api_base_url}/map",
                    params={"bbox": ",".join(str(value) for value in box)},
                )
                for box in boxes
            )
        )
        for response in responses:
            response.raise_for_status()
            xml_documents.append(response.text)

    nodes: Dict[int, Dict[str, Any]] = {}
    way_elements: Dict[int, Dict[str, Any]] = {}
    for xml_text in xml_documents:
        root = parse_xml(xml_text)
        for element in root:
            local = _local_name(element.tag)
            if local == "node":
                node_id = int(element.get("id", "0"))
                nodes[node_id] = {
                    "type": "node",
                    "id": node_id,
                    "lat": float(element.get("lat", "0")),
                    "lon": float(element.get("lon", "0")),
                    "version": int(element.get("version", "0")),
                }
            elif local == "way":
                tags = {
                    tag.get("k", ""): tag.get("v", "") for tag in element.findall("tag")
                }
                if "highway" not in tags:
                    continue
                way_id = int(element.get("id", "0"))
                way_elements[way_id] = {
                    "type": "way",
                    "id": way_id,
                    "nodes": [int(nd.get("ref", "0")) for nd in element.findall("nd")],
                    "tags": tags,
                }

    ways: List[Dict[str, Any]] = []
    highway_node_ids: set[int] = set()
    for way in way_elements.values():
        node_ids = way["nodes"]
        if any(node_id not in nodes for node_id in node_ids):
            continue
        highway_node_ids.update(node_ids)
        ways.append(
            {
                **way,
                "geometry": [
                    {"lat": nodes[node_id]["lat"], "lon": nodes[node_id]["lon"]}
                    for node_id in node_ids
                ],
            }
        )
    return ways, {
        node_id: nodes[node_id] for node_id in highway_node_ids if node_id in nodes
    }


def _candidate_metrics(
    track: Sequence[Point], geometry: Sequence[Point], radius_m: float
) -> Dict[str, Any]:
    distances = [_nearest_on_polyline(point, geometry)[0] for point in track]
    within = sum(distance <= radius_m for distance in distances)
    geometry_center = geometry[len(geometry) // 2]
    order = _nearest_on_polyline(geometry_center, track)[4]
    mean = sum(distances) / len(distances)
    maximum = max(distances)
    coverage = 100.0 * within / len(distances)
    score = coverage - min(100.0, mean * 2.0)
    return {
        "mean_distance_m": round(mean, 2),
        "max_distance_m": round(maximum, 2),
        "track_coverage_percent": round(coverage, 1),
        "order_along_track": round(order, 4),
        "match_score": round(score, 2),
    }


def _likely_chains(candidates: Sequence[Dict[str, Any]]) -> List[List[int]]:
    remaining = {candidate["way_id"]: candidate for candidate in candidates}
    chains: List[List[int]] = []
    while remaining:
        way_id, seed = remaining.popitem()
        component = [seed]
        known_nodes = set(seed.get("node_ids", []))
        changed = True
        while changed:
            changed = False
            for other_id, other in list(remaining.items()):
                if known_nodes.intersection(other.get("node_ids", [])):
                    component.append(other)
                    known_nodes.update(other.get("node_ids", []))
                    del remaining[other_id]
                    changed = True
        component.sort(key=lambda item: item["order_along_track"])
        chains.append([item["way_id"] for item in component])
    chains.sort(key=len, reverse=True)
    return chains


def _parse_way_full(xml_text: str, expected_way_id: int) -> Dict[str, Any]:
    root = parse_xml(xml_text)
    nodes: Dict[int, Dict[str, Any]] = {}
    selected: Optional[ET.Element] = None
    for element in root:
        local = _local_name(element.tag)
        if local == "node":
            node_id = int(element.get("id", "0"))
            nodes[node_id] = {
                "id": node_id,
                "lat": float(element.get("lat", "0")),
                "lon": float(element.get("lon", "0")),
                "version": int(element.get("version", "0")),
                "tags": {
                    tag.get("k", ""): tag.get("v", "") for tag in element.findall("tag")
                },
            }
        elif local == "way" and int(element.get("id", "0")) == expected_way_id:
            selected = element
    if selected is None:
        raise ValueError(f"Way {expected_way_id} not found in full response")
    node_ids = [int(nd.get("ref", "0")) for nd in selected.findall("nd")]
    if any(node_id not in nodes for node_id in node_ids):
        raise ValueError(f"Way {expected_way_id} response is missing referenced nodes")
    return {
        "id": expected_way_id,
        "version": int(selected.get("version", "0")),
        "node_ids": node_ids,
        "nodes": nodes,
        "tags": {tag.get("k", ""): tag.get("v", "") for tag in selected.findall("tag")},
    }


async def _fetch_way_full(client: Any, way_id: int) -> Dict[str, Any]:
    response = await client.get(f"{config.current_api_base_url}/way/{way_id}/full")
    if response.status_code != 200:
        raise ValueError(f"Could not fetch way {way_id}: HTTP {response.status_code}")
    return _parse_way_full(response.text, way_id)


async def _fetch_api_limits(client: Any) -> Tuple[int, int]:
    response = await client.get(f"{config.current_api_base_url}/capabilities")
    if response.status_code != 200:
        return MAX_WAY_NODES_FALLBACK, MAX_CHANGESET_ELEMENTS_FALLBACK
    try:
        root = parse_xml(response.text)
        waynodes = root.find(".//waynodes")
        changesets = root.find(".//changesets")
        return (
            (
                int(waynodes.get("maximum", MAX_WAY_NODES_FALLBACK))
                if waynodes is not None
                else MAX_WAY_NODES_FALLBACK
            ),
            (
                int(changesets.get("maximum_elements", MAX_CHANGESET_ELEMENTS_FALLBACK))
                if changesets is not None
                else MAX_CHANGESET_ELEMENTS_FALLBACK
            ),
        )
    except (ET.ParseError, TypeError, ValueError):
        return MAX_WAY_NODES_FALLBACK, MAX_CHANGESET_ELEMENTS_FALLBACK


async def _node_is_protected(client: Any, node: Dict[str, Any]) -> bool:
    if node.get("tags"):
        return True
    node_id = node["id"]
    ways_response, relations_response = await asyncio.gather(
        client.get(f"{config.current_api_base_url}/node/{node_id}/ways"),
        client.get(f"{config.current_api_base_url}/node/{node_id}/relations"),
    )
    if ways_response.status_code != 200 or relations_response.status_code != 200:
        # Failure to prove a node disposable must keep it protected.
        return True
    ways_root = parse_xml(ways_response.text)
    relations_root = parse_xml(relations_response.text)
    return len(ways_root.findall(".//way")) > 1 or bool(
        relations_root.findall(".//relation")
    )


async def _node_protection_flags(
    client: Any, nodes: Sequence[Dict[str, Any]], concurrency: int = 8
) -> List[bool]:
    """Check node parentage without flooding the editing API."""
    semaphore = asyncio.Semaphore(concurrency)

    async def check(node: Dict[str, Any]) -> bool:
        async with semaphore:
            return await _node_is_protected(client, node)

    return list(await asyncio.gather(*(check(node) for node in nodes)))


def _orient_way_chain(ways: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not ways:
        raise ValueError("At least one target way ID is required")

    def try_first(reverse_first: bool) -> Optional[List[Dict[str, Any]]]:
        result: List[Dict[str, Any]] = []
        first_ids = list(ways[0]["node_ids"])
        if reverse_first:
            first_ids.reverse()
        result.append(
            {**ways[0], "oriented_node_ids": first_ids, "reversed": reverse_first}
        )
        for way in ways[1:]:
            ids = list(way["node_ids"])
            if result[-1]["oriented_node_ids"][-1] == ids[0]:
                reversed_way = False
            elif result[-1]["oriented_node_ids"][-1] == ids[-1]:
                ids.reverse()
                reversed_way = True
            else:
                return None
            result.append({**way, "oriented_node_ids": ids, "reversed": reversed_way})
        return result

    oriented = try_first(False) or try_first(True)
    if oriented is None:
        raise ValueError(
            "Selected target ways are not a contiguous endpoint-to-endpoint chain"
        )
    return oriented


def _chain_nodes(oriented: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for way_index, way in enumerate(oriented):
        for node_index, node_id in enumerate(way["oriented_node_ids"]):
            if way_index and node_index == 0:
                continue
            result.append(way["nodes"][node_id])
    return result


def _nearest_anchor(
    point: Point, nodes: Sequence[Dict[str, Any]], max_distance_m: float
) -> Tuple[int, float, bool]:
    ranked = sorted(
        (
            _haversine_m(point, (node["lat"], node["lon"])),
            index,
        )
        for index, node in enumerate(nodes)
    )
    if not ranked or ranked[0][0] > max_distance_m:
        raise ValueError(
            f"Track endpoint is {ranked[0][0]:.1f}m from the nearest target node; "
            f"maximum alignment distance is {max_distance_m:.1f}m"
            if ranked
            else "Target way has no nodes"
        )
    ambiguous = (
        len(ranked) > 1
        and ranked[1][0] - ranked[0][0] < 2.0
        and abs(ranked[1][1] - ranked[0][1]) > 1
    )
    return ranked[0][1], ranked[0][0], ambiguous


def _purge_proposals() -> None:
    now = time.time()
    for proposal_id in list(_PROPOSALS):
        if _PROPOSALS[proposal_id].expires_at <= now:
            del _PROPOSALS[proposal_id]


def _store_proposal(payload: Dict[str, Any]) -> Proposal:
    _purge_proposals()
    created = time.time()
    proposal = Proposal(
        proposal_id=str(uuid.uuid4()),
        created_at=created,
        expires_at=created + config.osm_track_proposal_ttl_seconds,
        payload=payload,
    )
    _PROPOSALS[proposal.proposal_id] = proposal
    return proposal


def _proposal_result(
    proposal: Proposal,
    current_geojson: Dict[str, Any],
    proposed_geojson: Dict[str, Any],
) -> Dict[str, Any]:
    payload = proposal.payload
    return {
        "success": not payload["blocking_issues"],
        "data": {
            "proposal_id": proposal.proposal_id,
            "expires_at_unix": proposal.expires_at,
            "action": payload["action"],
            "segment_id": payload["segment_id"],
            "track_hash": payload["track_hash"],
            "summary": payload["summary"],
            "endpoint_snaps": payload.get("endpoint_snaps", []),
            "preserved_nodes": payload.get("preserved_nodes", []),
            "conditional_deletions": [
                node["id"] for node in payload.get("delete_nodes", [])
            ],
            "warnings": payload["warnings"],
            "blocking_issues": payload["blocking_issues"],
            "current_geojson": current_geojson,
            "proposed_geojson": proposed_geojson,
            "confirmation_required": True,
        },
        "message": (
            "Track edit preview is ready for explicit confirmation"
            if not payload["blocking_issues"]
            else "Track edit preview contains blocking issues and cannot be applied"
        ),
    }


@mcp.tool()
async def analyze_gpx_track(
    gpx_xml: Optional[str] = None, gpx_path: Optional[str] = None
) -> Dict[str, Any]:
    """Inspect a GPX file and list its independently selectable track segments."""
    try:
        digest, source, segments = _load_track(gpx_xml, gpx_path)
        segment_results = []
        warnings: List[str] = []
        for segment in segments:
            segment_warnings: List[str] = []
            discontinuities = _segment_discontinuities(segment)
            if not any(segment.times):
                segment_warnings.append(
                    "Segment has no timestamps; timestamps are optional for map editing"
                )
            if len(segment.points) < 2:
                segment_warnings.append("Segment cannot form a road")
            if discontinuities:
                largest = max(item["distance_m"] for item in discontinuities)
                segment_warnings.append(
                    f"Segment has {len(discontinuities)} discontinuous GPS jump(s), "
                    f"largest {largest:.1f}m; crop or split before road editing"
                )
            segment_results.append(
                {
                    "segment_id": segment.segment_id,
                    "name": segment.name,
                    "point_count": len(segment.points),
                    "distance_m": round(_length_m(segment.points), 2),
                    "bounds": _bounds(segment.points),
                    "start_time": next((item for item in segment.times if item), None),
                    "end_time": next(
                        (item for item in reversed(segment.times) if item), None
                    ),
                    "discontinuity_count": len(discontinuities),
                    "discontinuities": discontinuities[:20],
                    "warnings": segment_warnings,
                }
            )
        if len(segments) > 1:
            warnings.append(
                "GPX has multiple segments; choose exactly one segment_id for each preview"
            )
        return {
            "success": True,
            "data": {
                "track_hash": digest,
                "source": source,
                "segment_count": len(segments),
                "segments": segment_results,
                "warnings": warnings,
            },
            "message": f"Analyzed {len(segments)} GPX track segment(s)",
        }
    except Exception as exc:
        return _failure(
            type(exc).__name__,
            "Failed to analyze GPX",
            detail=describe_exception(exc),
        )


@mcp.tool()
async def suggest_track_road_candidates(
    segment_id: str,
    gpx_xml: Optional[str] = None,
    gpx_path: Optional[str] = None,
    limit: int = 10,
    search_radius_m: float = 30.0,
) -> Dict[str, Any]:
    """Suggest nearby OSM highway ways without selecting or modifying any way."""
    try:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if not 1 <= search_radius_m <= 500:
            raise ValueError("search_radius_m must be between 1 and 500")
        digest, _, segments = _load_track(gpx_xml, gpx_path)
        segment = _select_segment(segments, segment_id)
        _require_continuous_segment(segment)
        track = _simplify(segment.points, DEFAULT_SIMPLIFY_TOLERANCE_M)
        ways, _ = await _nearby_highways(track, search_radius_m)
        candidates: List[Dict[str, Any]] = []
        for way in ways:
            geometry = [
                (float(point["lat"]), float(point["lon"]))
                for point in way.get("geometry", [])
            ]
            if len(geometry) < 2:
                continue
            metrics = _candidate_metrics(track, geometry, search_radius_m)
            candidates.append(
                {
                    "way_id": int(way["id"]),
                    "tags": way.get("tags", {}),
                    "node_ids": [int(item) for item in way.get("nodes", [])],
                    **metrics,
                }
            )
        candidates.sort(key=lambda item: item["match_score"], reverse=True)
        candidates = candidates[:limit]
        return {
            "success": True,
            "data": {
                "track_hash": digest,
                "segment_id": segment_id,
                "candidates": candidates,
                "suggested_order": [
                    item["way_id"]
                    for item in sorted(
                        candidates, key=lambda item: item["order_along_track"]
                    )
                ],
                "likely_chains": _likely_chains(candidates),
                "selection_required": True,
            },
            "message": f"Found {len(candidates)} candidate road ways",
        }
    except Exception as exc:
        return _failure(
            type(exc).__name__,
            "Failed to suggest road candidates",
            detail=describe_exception(exc),
        )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    origin = a
    ax, ay = _xy_m(a, origin)
    bx, by = _xy_m(b, origin)
    cx, cy = _xy_m(c, origin)
    dx, dy = _xy_m(d, origin)

    def orientation(
        p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]
    ) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    return (
        orientation((ax, ay), (bx, by), (cx, cy))
        * orientation((ax, ay), (bx, by), (dx, dy))
        < 0
        and orientation((cx, cy), (dx, dy), (ax, ay))
        * orientation((cx, cy), (dx, dy), (bx, by))
        < 0
    )


async def _preview_create(
    track_hash: str,
    segment: TrackSegment,
    tags: Dict[str, str],
    comment: str,
    source: str,
    simplify_tolerance_m: float,
    endpoint_snap_tolerance_m: float,
) -> Dict[str, Any]:
    if not tags.get("highway"):
        raise ValueError("Creating a road requires an explicit highway=* tag")
    points = _simplify(segment.points, simplify_tolerance_m)
    if len(points) < 2:
        raise ValueError("Simplified track must contain at least two points")

    nearby_ways, nearby_nodes = await _nearby_highways(
        points, max(30.0, endpoint_snap_tolerance_m)
    )
    endpoint_snaps: List[Dict[str, Any]] = []
    snapped_refs: Dict[int, int] = {}
    snapshot_nodes: Dict[int, Dict[str, Any]] = {}
    for point_index in (0, len(points) - 1):
        ranked = sorted(
            (
                _haversine_m(point, (float(node["lat"]), float(node["lon"]))),
                node_id,
                node,
            )
            for node_id, node in nearby_nodes.items()
            for point in [points[point_index]]
        )
        if ranked and ranked[0][0] <= endpoint_snap_tolerance_m:
            distance, node_id, node = ranked[0]
            snapped_refs[point_index] = node_id
            snapshot_nodes[node_id] = {
                "id": node_id,
                "version": int(node.get("version", 0)),
            }
            endpoint_snaps.append(
                {
                    "endpoint": "start" if point_index == 0 else "end",
                    "node_id": node_id,
                    "distance_m": round(distance, 2),
                }
            )

    create_nodes: List[Dict[str, Any]] = []
    refs: List[int] = []
    next_temp = -1
    for index, point in enumerate(points):
        if index in snapped_refs:
            refs.append(snapped_refs[index])
        else:
            refs.append(next_temp)
            create_nodes.append(
                {"id": next_temp, "lat": point[0], "lon": point[1], "tags": {}}
            )
            next_temp -= 1

    warnings = [
        "A single GPS trace can be offset by several metres; compare the preview "
        "with other permitted evidence before applying."
    ]
    crossing_way_ids: List[int] = []
    for way in nearby_ways:
        geometry = [
            (float(item["lat"]), float(item["lon"])) for item in way.get("geometry", [])
        ]
        if any(
            _segments_intersect(a, b, c, d)
            for a, b in zip(points, points[1:])
            for c, d in zip(geometry, geometry[1:])
        ):
            crossing_way_ids.append(int(way["id"]))
    if crossing_way_ids:
        warnings.append(
            "Proposed road crosses existing ways but no at-grade connections will "
            f"be inferred: {sorted(set(crossing_way_ids))}"
        )

    async with get_authenticated_client() as client:
        for node_id in list(snapshot_nodes):
            response = await client.get(f"{config.current_api_base_url}/node/{node_id}")
            if response.status_code != 200:
                raise ValueError(
                    f"Could not verify snapped endpoint node {node_id}: "
                    f"HTTP {response.status_code}"
                )
            root = parse_xml(response.text)
            node = root.find(".//node")
            if node is None or node.get("version") is None:
                raise ValueError(
                    f"Could not determine version for snapped endpoint node {node_id}"
                )
            snapshot_nodes[node_id]["version"] = int(node.get("version", "0"))
            authoritative_point = (
                float(node.get("lat", "0")),
                float(node.get("lon", "0")),
            )
            for point_index, snapped_node_id in snapped_refs.items():
                if snapped_node_id == node_id:
                    points[point_index] = authoritative_point
        max_way_nodes, server_max_changes = await _fetch_api_limits(client)
    blocking: List[str] = []
    if len(refs) > max_way_nodes:
        blocking.append(
            f"Proposed way has {len(refs)} nodes; API maximum is {max_way_nodes}"
        )
    operation_count = len(create_nodes) + 1
    local_limit = min(config.max_changeset_size, server_max_changes)
    if operation_count > local_limit:
        blocking.append(
            f"Proposal has {operation_count} element operations; configured limit is {local_limit}"
        )

    payload = {
        "action": "create",
        "track_hash": track_hash,
        "segment_id": segment.segment_id,
        "changeset_comment": comment,
        "changeset_source": source,
        "create_nodes": create_nodes,
        "create_ways": [{"id": -1_000_000, "node_ids": refs, "tags": tags}],
        "modify_ways": [],
        "delete_nodes": [],
        "snapshot_ways": {},
        "snapshot_nodes": snapshot_nodes,
        "endpoint_snaps": endpoint_snaps,
        "preserved_nodes": list(snapped_refs.values()),
        "warnings": warnings,
        "blocking_issues": blocking,
        "summary": {
            "new_nodes": len(create_nodes),
            "new_ways": 1,
            "modified_ways": 0,
            "conditional_node_deletions": 0,
            "element_operations": operation_count,
        },
    }
    proposal = _store_proposal(payload)
    return _proposal_result(
        proposal,
        _feature_collection([]),
        _feature_collection([_line_feature(points, {"action": "create"})]),
    )


async def _preview_update(
    track_hash: str,
    segment: TrackSegment,
    target_way_ids: Sequence[int],
    comment: str,
    source: str,
    simplify_tolerance_m: float,
    max_alignment_distance_m: float,
) -> Dict[str, Any]:
    if not target_way_ids:
        raise ValueError("Updating a road requires ordered target_way_ids")
    if len(set(target_way_ids)) != len(target_way_ids):
        raise ValueError("target_way_ids must not contain duplicates")
    async with get_authenticated_client() as client:
        fetched = await asyncio.gather(
            *(_fetch_way_full(client, int(way_id)) for way_id in target_way_ids)
        )
        max_way_nodes, server_max_changes = await _fetch_api_limits(client)
        oriented = _orient_way_chain(fetched)
        chain_nodes = _chain_nodes(oriented)
        track = _simplify(segment.points, simplify_tolerance_m)

        start_index, start_distance, start_ambiguous = _nearest_anchor(
            track[0], chain_nodes, max_alignment_distance_m
        )
        end_index, end_distance, end_ambiguous = _nearest_anchor(
            track[-1], chain_nodes, max_alignment_distance_m
        )
        if start_index > end_index:
            track.reverse()
            start_index, start_distance, start_ambiguous = _nearest_anchor(
                track[0], chain_nodes, max_alignment_distance_m
            )
            end_index, end_distance, end_ambiguous = _nearest_anchor(
                track[-1], chain_nodes, max_alignment_distance_m
            )
        if start_index >= end_index:
            raise ValueError(
                "Track endpoints do not define a forward span on the way chain"
            )
        if chain_nodes[start_index]["id"] not in oriented[0]["oriented_node_ids"]:
            raise ValueError("Track start must anchor on the first selected target way")
        if chain_nodes[end_index]["id"] not in oriented[-1]["oriented_node_ids"]:
            raise ValueError("Track end must anchor on the last selected target way")

        blocking: List[str] = []
        if start_ambiguous or end_ambiguous:
            blocking.append("One or both splice anchors are ambiguous")

        selected_chain_nodes = chain_nodes[start_index : end_index + 1]
        protected_flags = await _node_protection_flags(client, selected_chain_nodes)

    # Anchors and every chain boundary are topology-critical even if otherwise
    # untagged and single-use.
    boundary_ids = {way["oriented_node_ids"][0] for way in oriented} | {
        way["oriented_node_ids"][-1] for way in oriented
    }
    marker_nodes: List[Dict[str, Any]] = []
    for offset, (node, protected) in enumerate(
        zip(selected_chain_nodes, protected_flags)
    ):
        chain_index = start_index + offset
        if (
            protected
            or node["id"] in boundary_ids
            or chain_index in (start_index, end_index)
        ):
            marker_nodes.append(node)

    marker_entries: List[Dict[str, Any]] = []
    last_fraction = -1.0
    for node in marker_nodes:
        point = (node["lat"], node["lon"])
        distance, _, _, _, fraction = _nearest_on_polyline(point, track)
        if distance > max_alignment_distance_m:
            blocking.append(
                f"Protected node {node['id']} is {distance:.1f}m from the proposed track"
            )
        if fraction + 1e-6 < last_fraction:
            blocking.append(
                "Protected nodes do not occur in track order; selected way chain is ambiguous"
            )
        last_fraction = max(last_fraction, fraction)
        marker_entries.append(
            {"node": node, "fraction": fraction, "distance_m": distance}
        )

    # Force splice anchors to the track endpoints. This keeps the untouched
    # prefix/suffix exact and never moves the existing anchor nodes.
    marker_entries[0]["fraction"] = 0.0
    marker_entries[-1]["fraction"] = 1.0

    next_temp = -1
    create_nodes: List[Dict[str, Any]] = []
    replacement_refs: List[int] = []
    replacement_coords: List[Point] = []
    marker_ref_positions: Dict[int, int] = {}
    for index, marker in enumerate(marker_entries):
        node = marker["node"]
        if index == 0:
            replacement_refs.append(node["id"])
            replacement_coords.append((node["lat"], node["lon"]))
            marker_ref_positions[node["id"]] = 0
            continue
        previous = marker_entries[index - 1]
        interval = _slice_line(track, previous["fraction"], marker["fraction"])
        interval = _simplify(interval, simplify_tolerance_m)
        for point in interval[1:-1]:
            replacement_refs.append(next_temp)
            replacement_coords.append(point)
            create_nodes.append(
                {"id": next_temp, "lat": point[0], "lon": point[1], "tags": {}}
            )
            next_temp -= 1
        replacement_refs.append(node["id"])
        replacement_coords.append((node["lat"], node["lon"]))
        marker_ref_positions[node["id"]] = len(replacement_refs) - 1

    modify_ways: List[Dict[str, Any]] = []
    proposed_features: List[Dict[str, Any]] = []
    current_features: List[Dict[str, Any]] = []
    retained_refs: set[int] = set()
    for way_index, way in enumerate(oriented):
        ids = way["oriented_node_ids"]
        current_features.append(
            _line_feature(
                [
                    (way["nodes"][node_id]["lat"], way["nodes"][node_id]["lon"])
                    for node_id in ids
                ],
                {"way_id": way["id"], "state": "current"},
            )
        )
        local_start = 0
        local_end = len(ids) - 1
        if way_index == 0:
            start_id = chain_nodes[start_index]["id"]
            local_start = ids.index(start_id)
        else:
            start_id = ids[0]
        if way_index == len(oriented) - 1:
            end_id = chain_nodes[end_index]["id"]
            local_end = ids.index(end_id)
        else:
            end_id = ids[-1]
        if local_start >= local_end:
            blocking.append(f"Way {way['id']} has no replaceable span between anchors")
            proposed_ids = ids
        else:
            replacement_start = marker_ref_positions[start_id]
            replacement_end = marker_ref_positions[end_id]
            proposed_ids = (
                ids[:local_start]
                + replacement_refs[replacement_start : replacement_end + 1]
                + ids[local_end + 1 :]
            )
        if way["reversed"]:
            proposed_ids = list(reversed(proposed_ids))
        retained_refs.update(node_id for node_id in proposed_ids if node_id > 0)
        modify_ways.append(
            {
                "id": way["id"],
                "version": way["version"],
                "node_ids": proposed_ids,
                "tags": way["tags"],
            }
        )
        coords = []
        created_by_id = {node["id"]: node for node in create_nodes}
        for node_id in proposed_ids:
            node = created_by_id.get(node_id) or way["nodes"].get(node_id)
            if node is None:
                # A positive node from an adjacent way is available in fetched.
                node = next(
                    candidate["nodes"].get(node_id)
                    for candidate in oriented
                    if candidate["nodes"].get(node_id) is not None
                )
            coords.append((node["lat"], node["lon"]))
        proposed_features.append(
            _line_feature(coords, {"way_id": way["id"], "state": "proposed"})
        )

    all_nodes: Dict[int, Dict[str, Any]] = {}
    for way in oriented:
        all_nodes.update(way["nodes"])
    replaceable_ids = {node["id"] for node in selected_chain_nodes}
    protected_ids = {entry["node"]["id"] for entry in marker_entries}
    delete_nodes = [
        all_nodes[node_id]
        for node_id in sorted(replaceable_ids - retained_refs - protected_ids)
    ]

    operation_count = len(create_nodes) + len(modify_ways) + len(delete_nodes)
    local_limit = min(config.max_changeset_size, server_max_changes)
    if operation_count > local_limit:
        blocking.append(
            f"Proposal has {operation_count} element operations; configured limit is {local_limit}"
        )
    for way in modify_ways:
        if len(way["node_ids"]) > max_way_nodes:
            blocking.append(
                f"Way {way['id']} would have {len(way['node_ids'])} nodes; API maximum is {max_way_nodes}"
            )

    warnings = [
        "A single GPS trace can be offset by several metres; compare the preview "
        "with other permitted evidence before applying."
    ]
    payload = {
        "action": "update",
        "track_hash": track_hash,
        "segment_id": segment.segment_id,
        "changeset_comment": comment,
        "changeset_source": source,
        "create_nodes": create_nodes,
        "create_ways": [],
        "modify_ways": modify_ways,
        "delete_nodes": delete_nodes,
        "snapshot_ways": {
            str(way["id"]): {
                "version": way["version"],
                "node_ids": way["node_ids"],
                "tags": way["tags"],
            }
            for way in fetched
        },
        "snapshot_nodes": {
            str(node_id): {"version": all_nodes[node_id]["version"]}
            for node_id in protected_ids | {node["id"] for node in delete_nodes}
        },
        "endpoint_snaps": [
            {
                "endpoint": "start",
                "node_id": chain_nodes[start_index]["id"],
                "distance_m": round(start_distance, 2),
            },
            {
                "endpoint": "end",
                "node_id": chain_nodes[end_index]["id"],
                "distance_m": round(end_distance, 2),
            },
        ],
        "preserved_nodes": sorted(protected_ids),
        "warnings": warnings,
        "blocking_issues": list(dict.fromkeys(blocking)),
        "summary": {
            "new_nodes": len(create_nodes),
            "new_ways": 0,
            "modified_ways": len(modify_ways),
            "conditional_node_deletions": len(delete_nodes),
            "element_operations": operation_count,
        },
    }
    proposal = _store_proposal(payload)
    return _proposal_result(
        proposal,
        _feature_collection(current_features),
        _feature_collection(proposed_features),
    )


@mcp.tool()
async def preview_track_road_edit(
    action: str,
    segment_id: str,
    changeset_comment: str,
    changeset_source: str,
    gpx_xml: Optional[str] = None,
    gpx_path: Optional[str] = None,
    target_way_ids: Optional[List[int]] = None,
    tags: Optional[Dict[str, str]] = None,
    simplify_tolerance_m: float = DEFAULT_SIMPLIFY_TOLERANCE_M,
    endpoint_snap_tolerance_m: float = DEFAULT_ENDPOINT_SNAP_M,
    max_alignment_distance_m: float = DEFAULT_MAX_ALIGNMENT_M,
) -> Dict[str, Any]:
    """Build a non-writing GeoJSON and element diff preview for a road edit."""
    try:
        action = action.lower().strip()
        if action not in {"create", "update"}:
            raise ValueError("action must be 'create' or 'update'")
        if not changeset_comment.strip():
            raise ValueError("changeset_comment must not be empty")
        if not changeset_source.strip():
            raise ValueError("changeset_source must not be empty")
        if not 0 <= simplify_tolerance_m <= 100:
            raise ValueError("simplify_tolerance_m must be between 0 and 100")
        if not 0 <= endpoint_snap_tolerance_m <= 100:
            raise ValueError("endpoint_snap_tolerance_m must be between 0 and 100")
        if not 1 <= max_alignment_distance_m <= 100:
            raise ValueError("max_alignment_distance_m must be between 1 and 100")
        digest, _, segments = _load_track(gpx_xml, gpx_path)
        segment = _select_segment(segments, segment_id)
        _require_continuous_segment(segment)
        if action == "create":
            if target_way_ids:
                raise ValueError("target_way_ids are not allowed for action=create")
            return await _preview_create(
                digest,
                segment,
                tags or {},
                changeset_comment.strip(),
                changeset_source.strip(),
                simplify_tolerance_m,
                endpoint_snap_tolerance_m,
            )
        if tags:
            raise ValueError("Track updates preserve existing way tags; omit tags")
        return await _preview_update(
            digest,
            segment,
            target_way_ids or [],
            changeset_comment.strip(),
            changeset_source.strip(),
            simplify_tolerance_m,
            max_alignment_distance_m,
        )
    except Exception as exc:
        return _failure(
            type(exc).__name__,
            "Failed to preview track road edit",
            detail=describe_exception(exc),
        )


def _append_tags(parent: ET.Element, tags: Dict[str, str]) -> None:
    for key, value in tags.items():
        ET.SubElement(parent, "tag", {"k": str(key), "v": str(value)})


def _build_osm_change(payload: Dict[str, Any], changeset_id: int) -> str:
    root = ET.Element("osmChange", {"version": "0.6", "generator": "osm-edit-mcp"})
    if payload["create_nodes"] or payload["create_ways"]:
        create = ET.SubElement(root, "create")
        for node in payload["create_nodes"]:
            element = ET.SubElement(
                create,
                "node",
                {
                    "id": str(node["id"]),
                    "changeset": str(changeset_id),
                    "lat": str(node["lat"]),
                    "lon": str(node["lon"]),
                },
            )
            _append_tags(element, node.get("tags", {}))
        for way in payload["create_ways"]:
            element = ET.SubElement(
                create,
                "way",
                {"id": str(way["id"]), "changeset": str(changeset_id)},
            )
            for node_id in way["node_ids"]:
                ET.SubElement(element, "nd", {"ref": str(node_id)})
            _append_tags(element, way["tags"])

    if payload["modify_ways"]:
        modify = ET.SubElement(root, "modify")
        for way in payload["modify_ways"]:
            element = ET.SubElement(
                modify,
                "way",
                {
                    "id": str(way["id"]),
                    "version": str(way["version"]),
                    "changeset": str(changeset_id),
                },
            )
            for node_id in way["node_ids"]:
                ET.SubElement(element, "nd", {"ref": str(node_id)})
            _append_tags(element, way["tags"])

    if payload["delete_nodes"]:
        delete = ET.SubElement(root, "delete", {"if-unused": "true"})
        for node in payload["delete_nodes"]:
            ET.SubElement(
                delete,
                "node",
                {
                    "id": str(node["id"]),
                    "version": str(node["version"]),
                    "changeset": str(changeset_id),
                    "lat": str(node["lat"]),
                    "lon": str(node["lon"]),
                },
            )
    return ET.tostring(root, encoding="unicode")


def _parse_diff_result(xml_text: str) -> List[Dict[str, Any]]:
    root = parse_xml(xml_text)
    results = []
    for element in root:
        item = {
            "type": _local_name(element.tag),
            "old_id": int(element.get("old_id", "0")),
            "new_id": int(element.get("new_id", element.get("old_id", "0"))),
            "new_version": int(element.get("new_version", "0")),
        }
        results.append(item)
    return results


async def _validate_proposal_versions(client: Any, payload: Dict[str, Any]) -> None:
    for way_id_text, snapshot in payload.get("snapshot_ways", {}).items():
        way_id = int(way_id_text)
        current = await _fetch_way_full(client, way_id)
        if (
            current["version"] != snapshot["version"]
            or current["node_ids"] != snapshot["node_ids"]
            or current["tags"] != snapshot["tags"]
        ):
            raise ValueError(
                f"Way {way_id} changed after preview; create a fresh proposal"
            )
    for node_id_text, snapshot in payload.get("snapshot_nodes", {}).items():
        node_id = int(node_id_text)
        response = await client.get(f"{config.current_api_base_url}/node/{node_id}")
        if response.status_code != 200:
            raise ValueError(f"Referenced node {node_id} no longer exists")
        root = parse_xml(response.text)
        node = root.find(".//node")
        if node is None or int(node.get("version", "0")) != snapshot["version"]:
            raise ValueError(f"Referenced node {node_id} changed after preview")
    delete_nodes = payload.get("delete_nodes", [])
    if delete_nodes:
        protected = await _node_protection_flags(client, delete_nodes)
        newly_protected = [
            node["id"]
            for node, is_protected in zip(delete_nodes, protected)
            if is_protected
        ]
        if newly_protected:
            raise ValueError(
                "Nodes gained tags, parent ways, or relation memberships after "
                f"preview: {newly_protected}; create a fresh proposal"
            )


@mcp.tool()
async def apply_track_road_edit(
    proposal_id: str, confirm: bool, changeset_id: Optional[int] = None
) -> Dict[str, Any]:
    """Apply an unexpired track preview after an explicit confirmation."""
    if confirm is not True:
        return _failure(
            "Confirmation required",
            "Set confirm=true only after reviewing the complete preview",
        )
    _purge_proposals()
    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        return _failure(
            "Unknown or expired proposal",
            "Create a fresh preview before applying the road edit",
        )
    payload = proposal.payload
    if payload["blocking_issues"]:
        return _failure(
            "Proposal is blocked",
            "Resolve all blocking issues and create a fresh preview",
            blocking_issues=payload["blocking_issues"],
        )
    if not load_oauth_token():
        return _failure(
            "Authentication required",
            "Track edits require OAuth with the write_api scope",
        )

    owned_changeset = changeset_id is None
    active_changeset_id = changeset_id
    try:
        async with get_authenticated_client() as client:
            await _validate_proposal_versions(client, payload)

        if active_changeset_id is None:
            created: Dict[str, Any] = await create_changeset(
                payload["changeset_comment"],
                {"source": payload["changeset_source"]},
            )
            if not created.get("success"):
                return created
            active_changeset_id = int(created["data"]["changeset_id"])

        osm_change = _build_osm_change(payload, active_changeset_id)
        async with get_authenticated_client() as client:
            response = await client.post(
                f"{config.current_api_base_url}/changeset/{active_changeset_id}/upload",
                content=osm_change,
                headers={"Content-Type": "text/xml"},
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"OSM diff upload failed with HTTP {response.status_code}: {response.text}"
            )
        diff_results = _parse_diff_result(response.text)
        close_result = None
        if owned_changeset:
            close_result = await close_changeset(active_changeset_id)
        del _PROPOSALS[proposal_id]
        return {
            "success": True,
            "data": {
                "proposal_id": proposal_id,
                "changeset_id": active_changeset_id,
                "changeset_url": f"{config.current_api_base_url}/changeset/{active_changeset_id}",
                "diff_results": diff_results,
                "changeset_closed": bool(close_result and close_result.get("success")),
                "summary": payload["summary"],
            },
            "message": "Track road edit uploaded successfully",
        }
    except Exception as exc:
        if owned_changeset and active_changeset_id is not None:
            try:
                await close_changeset(active_changeset_id)
            except Exception:
                pass
        return _failure(
            type(exc).__name__,
            "Failed to apply track road edit; the osmChange upload is transactional",
            detail=describe_exception(exc),
            changeset_id=active_changeset_id,
        )


__all__ = [
    "analyze_gpx_track",
    "apply_track_road_edit",
    "preview_track_road_edit",
    "suggest_track_road_candidates",
]
