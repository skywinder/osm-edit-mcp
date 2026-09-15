"""Safe GPX-to-OSM road editing tools.

The public workflow is deliberately two phase: callers inspect/suggest/preview,
then explicitly apply an unexpired proposal.  Geometry writes use one
``osmChange`` upload so new nodes, way changes, and cleanup are transactional.
"""

import asyncio
import hashlib
import html
import json
import math
import os
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from defusedxml.ElementTree import fromstring as parse_xml
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .app import mcp, profile_resource, profile_tool
from .auth import verify_write_identity
from .config import config
from .http_client import (
    describe_exception,
    get_authenticated_client,
    get_public_client,
)
from .proposal_store import ProposalStore, ProposalStoreError
from .token_store import get_current_user_info, load_oauth_token
from .valhalla import match_track as valhalla_match_track
from .write_tools import close_changeset

Point = Tuple[float, float]  # (lat, lon)
MAX_WAY_NODES_FALLBACK = 2_000
MAX_CHANGESET_ELEMENTS_FALLBACK = 10_000
DEFAULT_SIMPLIFY_TOLERANCE_M = 3.0
DEFAULT_ENDPOINT_SNAP_M = 10.0
ENDPOINT_WAY_AMBIGUITY_M = 2.0
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
    digest: str = ""
    status: str = "PREVIEWED"
    api_target: str = ""
    osm_uid: Optional[int] = None


_PROPOSALS: Dict[str, Proposal] = {}
_PROPOSAL_STORE = ProposalStore(config.osm_proposal_db_path)


@dataclass(frozen=True)
class TrackRecord:
    track_id: str
    source: str
    segments: Tuple[TrackSegment, ...]


@dataclass(frozen=True)
class TrackSelection:
    selection_id: str
    track_id: str
    segment_id: str
    start_point_index: int
    end_point_index: int
    points: Tuple[Point, ...]
    times: Tuple[Optional[str], ...]


_TRACKS: Dict[str, TrackRecord] = {}
_TRACK_SELECTIONS: Dict[str, TrackSelection] = {}


class ApplyConfirmation(BaseModel):
    confirm: bool = Field(
        description="Confirm the exact proposal digest displayed in the review"
    )
    proposal_digest: str = Field(
        description="The complete SHA-256 proposal digest shown in the review"
    )


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
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(config.osm_track_max_file_bytes + 1)
        if len(raw) > config.osm_track_max_file_bytes:
            raise ValueError(
                f"GPX file exceeds {config.osm_track_max_file_bytes} bytes"
            )
        return raw.decode("utf-8"), str(resolved)
    finally:
        os.close(descriptor)


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
    _TRACKS[digest] = TrackRecord(
        track_id=digest,
        source=source,
        segments=tuple(segments),
    )
    return digest, source, segments


def _select_segment(segments: Sequence[TrackSegment], segment_id: str) -> TrackSegment:
    for segment in segments:
        if segment.segment_id == segment_id:
            if len(segment.points) < 2:
                raise ValueError("Selected segment must contain at least two points")
            return segment
    available = ", ".join(segment.segment_id for segment in segments)
    raise ValueError(f"Unknown segment_id {segment_id!r}; available: {available}")


def _parse_gpx_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _nearest_time_index(segment: TrackSegment, requested: str) -> int:
    target = _parse_gpx_time(requested)
    candidates = [
        (abs((_parse_gpx_time(value) - target).total_seconds()), index)
        for index, value in enumerate(segment.times)
        if value
    ]
    if not candidates:
        raise ValueError("Selected segment has no timestamps")
    return min(candidates)[1]


def _nearest_point_index(segment: TrackSegment, point: Point) -> int:
    return min(
        range(len(segment.points)),
        key=lambda index: _haversine_m(segment.points[index], point),
    )


def _resolve_track_selection(selection_id: str) -> TrackSelection:
    selection = _TRACK_SELECTIONS.get(selection_id)
    if selection is None:
        raise ValueError(
            "Unknown track selection; analyze the GPX and select the range again"
        )
    return selection


def _resolve_edit_segment(
    selection_id: Optional[str],
    segment_id: Optional[str],
    gpx_xml: Optional[str],
    gpx_path: Optional[str],
) -> Tuple[str, TrackSegment]:
    if selection_id:
        if gpx_xml is not None or gpx_path is not None:
            raise ValueError("selection_id cannot be combined with a GPX source")
        selection = _resolve_track_selection(selection_id)
        return selection.track_id, TrackSegment(
            segment_id=selection.selection_id,
            name=f"selection from {selection.segment_id}",
            points=selection.points,
            times=selection.times,
        )
    if not segment_id:
        raise ValueError("Provide segment_id or selection_id")
    digest, _, segments = _load_track(gpx_xml, gpx_path)
    return digest, _select_segment(segments, segment_id)


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
                    "version": int(element.get("version", "0")),
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
            _PROPOSAL_STORE.expire(proposal_id)
            del _PROPOSALS[proposal_id]


def _store_proposal(
    payload: Dict[str, Any], verified_osm_uid: Optional[int] = None
) -> Proposal:
    _purge_proposals()
    user_info = get_current_user_info() or {}
    raw_user_id = user_info.get("user_id")
    cached_uid = int(str(raw_user_id)) if raw_user_id not in {None, ""} else None
    osm_uid = verified_osm_uid if verified_osm_uid is not None else cached_uid
    stored = _PROPOSAL_STORE.create(
        proposal_id=str(uuid.uuid4()),
        payload=payload,
        api_target=config.current_api_base_url,
        osm_uid=osm_uid,
        ttl_seconds=config.osm_track_proposal_ttl_seconds,
    )
    proposal = Proposal(
        proposal_id=stored.proposal_id,
        created_at=stored.created_at,
        expires_at=stored.expires_at,
        payload=stored.payload,
        digest=stored.digest,
        status=stored.status,
        api_target=stored.api_target,
        osm_uid=stored.osm_uid,
    )
    _PROPOSALS[proposal.proposal_id] = proposal
    return proposal


def _refresh_proposal_digest(proposal: Proposal) -> None:
    proposal.digest = _PROPOSAL_STORE.replace_preview_payload(
        proposal.proposal_id,
        proposal.payload,
        proposal.api_target,
        proposal.osm_uid,
    )


def _get_proposal(proposal_id: str) -> Optional[Proposal]:
    cached = _PROPOSALS.get(proposal_id)
    if cached is not None:
        if cached.expires_at <= time.time() and cached.status in {
            "PREVIEWED",
            "AWAITING_APPROVAL",
        }:
            _PROPOSAL_STORE.expire(proposal_id)
            del _PROPOSALS[proposal_id]
            return None
        return cached
    stored = _PROPOSAL_STORE.get(proposal_id)
    if stored is None:
        return None
    proposal = Proposal(
        proposal_id=stored.proposal_id,
        created_at=stored.created_at,
        expires_at=stored.expires_at,
        payload=stored.payload,
        digest=stored.digest,
        status=stored.status,
        api_target=stored.api_target,
        osm_uid=stored.osm_uid,
    )
    _PROPOSALS[proposal_id] = proposal
    return proposal


def _proposal_result(
    proposal: Proposal,
    current_geojson: Dict[str, Any],
    proposed_geojson: Dict[str, Any],
) -> Dict[str, Any]:
    payload = proposal.payload
    payload["_review"] = {
        "current_geojson": current_geojson,
        "proposed_geojson": proposed_geojson,
    }
    _PROPOSAL_STORE.update_payload(proposal.proposal_id, payload)
    return {
        "success": not payload["blocking_issues"],
        "data": {
            "proposal_id": proposal.proposal_id,
            "proposal_digest": proposal.digest,
            "expires_at_unix": proposal.expires_at,
            "action": payload["action"],
            "segment_id": payload["segment_id"],
            "track_hash": payload["track_hash"],
            "summary": payload["summary"],
            "endpoint_snaps": payload.get("endpoint_snaps", []),
            "endpoint_way_connections": payload.get("endpoint_way_connections", []),
            "dangling_endpoints": payload.get("dangling_endpoints", []),
            "preserved_nodes": payload.get("preserved_nodes", []),
            "conditional_deletions": [
                node["id"] for node in payload.get("delete_nodes", [])
            ],
            "warnings": payload["warnings"],
            "blocking_issues": payload["blocking_issues"],
            "current_geojson": current_geojson,
            "proposed_geojson": proposed_geojson,
            "operations": {
                "create_nodes": payload.get("create_nodes", []),
                "create_ways": payload.get("create_ways", []),
                "modify_ways": payload.get("modify_ways", []),
                "delete_nodes": payload.get("delete_nodes", []),
            },
            "api_target": proposal.api_target,
            "osm_uid": proposal.osm_uid,
            "preview_uri": f"ui://osm-edit/proposal/{proposal.proposal_id}",
            "confirmation_required": True,
        },
        "message": (
            "Track edit preview is ready for explicit confirmation"
            if not payload["blocking_issues"]
            else "Track edit preview contains blocking issues and cannot be applied"
        ),
    }


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
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
                "track_id": digest,
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


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
async def create_track_selection(
    track_id: str,
    segment_id: str,
    start_point_index: Optional[int] = None,
    end_point_index: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    start_lat: Optional[float] = None,
    start_lon: Optional[float] = None,
    end_lat: Optional[float] = None,
    end_lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Select one continuous subsection of an analyzed GPX without copying it."""
    try:
        record = _TRACKS.get(track_id)
        if record is None:
            raise ValueError("Unknown track_id; analyze the GPX again")
        segment = _select_segment(record.segments, segment_id)
        modes = [
            start_point_index is not None or end_point_index is not None,
            start_time is not None or end_time is not None,
            any(
                value is not None for value in (start_lat, start_lon, end_lat, end_lon)
            ),
        ]
        if sum(modes) != 1:
            raise ValueError(
                "Choose exactly one range mode: point indexes, timestamps, or coordinates"
            )
        if modes[0]:
            if start_point_index is None or end_point_index is None:
                raise ValueError(
                    "Both start_point_index and end_point_index are required"
                )
            start_index, end_index = start_point_index, end_point_index
        elif modes[1]:
            if start_time is None or end_time is None:
                raise ValueError("Both start_time and end_time are required")
            start_index = _nearest_time_index(segment, start_time)
            end_index = _nearest_time_index(segment, end_time)
        else:
            if any(value is None for value in (start_lat, start_lon, end_lat, end_lon)):
                raise ValueError("Both start and end coordinates are required")
            assert start_lat is not None and start_lon is not None
            assert end_lat is not None and end_lon is not None
            start_index = _nearest_point_index(
                segment, (float(start_lat), float(start_lon))
            )
            end_index = _nearest_point_index(segment, (float(end_lat), float(end_lon)))

        if not 0 <= start_index < len(segment.points):
            raise ValueError("start point is outside the selected segment")
        if not 0 <= end_index < len(segment.points):
            raise ValueError("end point is outside the selected segment")
        if start_index == end_index:
            raise ValueError("Track selection must contain at least two points")
        if start_index < end_index:
            points = segment.points[start_index : end_index + 1]
            times = segment.times[start_index : end_index + 1]
        else:
            points = tuple(reversed(segment.points[end_index : start_index + 1]))
            times = tuple(reversed(segment.times[end_index : start_index + 1]))
        selected_segment = TrackSegment(
            segment_id="selection",
            name=segment.name,
            points=tuple(points),
            times=tuple(times),
        )
        _require_continuous_segment(selected_segment)
        selection_material = (
            f"{track_id}:{segment_id}:{start_index}:{end_index}"
        ).encode("utf-8")
        selection_id = hashlib.sha256(selection_material).hexdigest()[:32]
        selection = TrackSelection(
            selection_id=selection_id,
            track_id=track_id,
            segment_id=segment_id,
            start_point_index=start_index,
            end_point_index=end_index,
            points=tuple(points),
            times=tuple(times),
        )
        _TRACK_SELECTIONS[selection_id] = selection
        return {
            "success": True,
            "data": {
                "selection_id": selection_id,
                "track_id": track_id,
                "segment_id": segment_id,
                "start_point_index": start_index,
                "end_point_index": end_index,
                "point_count": len(points),
                "distance_m": round(_length_m(points), 2),
                "bounds": _bounds(points),
                "geojson": _feature_collection(
                    [_line_feature(points, {"state": "selected_gpx"})]
                ),
                "preview_uri": f"ui://osm-edit/track-selection/{selection_id}",
            },
            "message": "Selected a continuous GPX range",
        }
    except Exception as exc:
        return _failure(
            type(exc).__name__,
            "Failed to select GPX range",
            detail=describe_exception(exc),
        )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def match_track_selection(
    selection_id: str, costing: str = "auto"
) -> Dict[str, Any]:
    """Optionally map-match a GPX selection using a separately installed local
    Valhalla service. Configure OSM_VALHALLA_URL (default http://127.0.0.1:8002)
    with routing tiles for the survey area. No OAuth; GPX stays on loopback.
    This step can be skipped before suggest_track_road_candidates and preview.
    Routing results are diagnostic only, not evidence for OSM geometry.
    """
    try:
        selection = _resolve_track_selection(selection_id)
        result = await valhalla_match_track(selection.points, costing=costing)
        matched_percent = float(result["matched_percent"])
        if not result["unmatched_spans"] and matched_percent >= 90:
            classification = "existing"
        elif matched_percent >= 30:
            classification = "realign_candidate"
        else:
            classification = "unmatched"
        matched_geometry = result.pop("matched_geometry")
        return {
            "success": True,
            "data": {
                "selection_id": selection_id,
                "classification": classification,
                **result,
                "matched_geojson": _feature_collection(
                    [
                        _line_feature(
                            matched_geometry,
                            {"state": "valhalla_match", "evidence": False},
                        )
                    ]
                    if matched_geometry
                    else []
                ),
                "warning": (
                    "Routing output is diagnostic only and must not be copied as OSM geometry"
                ),
            },
            "message": f"Map matching classified the selection as {classification}",
        }
    except httpx.HTTPError as exc:
        return _failure(
            type(exc).__name__,
            "Local Valhalla map matching is unavailable or failed",
            detail=describe_exception(exc),
            selection_id=selection_id,
            optional=True,
            next_steps=[
                "Skip matching and call suggest_track_road_candidates with this selection_id",
                "Or start local Valhalla with tiles for the survey area and set OSM_VALHALLA_URL",
            ],
            documentation="https://github.com/skywinder/osm-edit-mcp/blob/main/docs/VALHALLA.md",
        )
    except Exception as exc:
        return _failure(
            type(exc).__name__,
            "Local Valhalla map matching is unavailable or failed",
            detail=describe_exception(exc),
            selection_id=selection_id,
        )


def _map_preview_html(title: str, layers: Dict[str, Dict[str, Any]]) -> str:
    """Render a dependency-free review map for MCP resource-capable hosts."""
    serialized = json.dumps(layers, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ margin:0; font:14px system-ui; background:#101418; color:#eef2f5; }}
header {{ padding:12px 16px; background:#182028; }}
canvas {{ width:100%; height:70vh; display:block; background:#e8eee4; }}
.legend {{ padding:10px 16px; display:flex; gap:18px; }}
.swatch {{ display:inline-block; width:18px; height:4px; margin-right:6px; }}
</style></head><body><header><strong>{html.escape(title)}</strong><br>
Review the exact geometry and warnings in the tool result before approval.</header>
<canvas id="map" width="1200" height="760"></canvas>
<div class="legend"><span><i class="swatch" style="background:#637381"></i>Current</span>
<span><i class="swatch" style="background:#e53935"></i>Proposed/selected</span></div>
<script>
const layers={serialized}; const canvas=document.getElementById('map');
const ctx=canvas.getContext('2d'); const lines=[];
for (const [name,fc] of Object.entries(layers)) for (const f of (fc.features||[])) {{
 const g=f.geometry||{{}}; if(g.type==='LineString') lines.push([name,g.coordinates]);
}}
const pts=lines.flatMap(x=>x[1]);
if(pts.length) {{
 const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
 const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
 const sx=(canvas.width-80)/Math.max(maxX-minX,1e-9), sy=(canvas.height-80)/Math.max(maxY-minY,1e-9);
 const scale=Math.min(sx,sy); const project=p=>[40+(p[0]-minX)*scale,canvas.height-40-(p[1]-minY)*scale];
 for(const [name,line] of lines) {{ ctx.beginPath(); ctx.strokeStyle=name==='current'?'#637381':'#e53935';
 ctx.lineWidth=name==='current'?7:4; line.forEach((p,i)=>{{const q=project(p); i?ctx.lineTo(...q):ctx.moveTo(...q)}}); ctx.stroke(); }}
}}
</script></body></html>"""


@profile_resource(
    "ui://osm-edit/track-selection/{selection_id}",
    name="OSM GPX track selection preview",
    description="Local visual preview of the selected GPX subsection",
    mime_type="text/html",
)
def track_selection_preview_resource(selection_id: str) -> str:
    selection = _resolve_track_selection(selection_id)
    return _map_preview_html(
        "Selected GPX range",
        {
            "selected": _feature_collection(
                [_line_feature(selection.points, {"state": "selected_gpx"})]
            )
        },
    )


@profile_resource(
    "ui://osm-edit/proposal/{proposal_id}",
    name="OSM edit proposal preview",
    description="Current and proposed OSM geometry for human review",
    mime_type="text/html",
)
def proposal_preview_resource(proposal_id: str) -> str:
    proposal = _get_proposal(proposal_id)
    if proposal is None:
        raise ValueError("Unknown or expired proposal")
    review = proposal.payload.get("_review", {})
    return _map_preview_html(
        f"OSM proposal {proposal_id}",
        {
            "current": review.get("current_geojson", _feature_collection([])),
            "proposed": review.get("proposed_geojson", _feature_collection([])),
        },
    )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def suggest_track_road_candidates(
    segment_id: Optional[str] = None,
    gpx_xml: Optional[str] = None,
    gpx_path: Optional[str] = None,
    limit: int = 10,
    search_radius_m: float = 30.0,
    selection_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Suggest nearby OSM highway ways without selecting or modifying any way."""
    try:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if not 1 <= search_radius_m <= 500:
            raise ValueError("search_radius_m must be between 1 and 500")
        digest, segment = _resolve_edit_segment(
            selection_id, segment_id, gpx_xml, gpx_path
        )
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
                    "version": int(way.get("version", 0)),
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
                "segment_id": segment.segment_id,
                "selection_id": selection_id,
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


def _grade_separation(tags: Dict[str, str]) -> Tuple[str, bool, bool]:
    layer = tags.get("layer", "0")
    bridge = tags.get("bridge", "no").lower() not in {"", "no", "false", "0"}
    tunnel = tags.get("tunnel", "no").lower() not in {"", "no", "false", "0"}
    return layer, bridge, tunnel


def _connection_grade_issue(
    proposed_tags: Dict[str, str], existing_tags: Dict[str, str]
) -> Optional[str]:
    proposed = _grade_separation(proposed_tags)
    existing = _grade_separation(existing_tags)
    if proposed == existing:
        return None
    if proposed != ("0", False, False) or existing != ("0", False, False):
        return (
            "layer/bridge/tunnel tags are incompatible with the proposed road "
            f"({proposed}) and connection way ({existing})"
        )
    return None


def _highway_context_snapshot(
    ways: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    return {
        str(int(way["id"])): {
            "version": int(way.get("version", 0)),
            "node_ids": [int(node_id) for node_id in way.get("nodes", [])],
            "tags": way.get("tags", {}),
        }
        for way in ways
    }


async def _preview_create(
    track_hash: str,
    segment: TrackSegment,
    tags: Dict[str, str],
    comment: str,
    source: str,
    simplify_tolerance_m: float,
    endpoint_snap_tolerance_m: float,
    connect_endpoints_to_ways: bool,
    verified_osm_uid: int,
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
    endpoint_way_connections: List[Dict[str, Any]] = []
    dangling_endpoints: List[Dict[str, Any]] = []
    snapped_refs: Dict[int, int] = {}
    snapshot_nodes: Dict[int, Dict[str, Any]] = {}
    pending_way_connections: Dict[int, Dict[str, Any]] = {}
    blocking: List[str] = []
    for point_index in (0, len(points) - 1):
        endpoint_name = "start" if point_index == 0 else "end"
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
            if (
                len(ranked) > 1
                and ranked[1][0] <= endpoint_snap_tolerance_m
                and ranked[1][0] - ranked[0][0] < ENDPOINT_WAY_AMBIGUITY_M
            ):
                candidate_ids = [item[1] for item in ranked[:5]]
                blocking.append(
                    f"{endpoint_name.capitalize()} endpoint is ambiguously close to "
                    f"multiple highway nodes: {candidate_ids}"
                )
                endpoint_snaps.append(
                    {
                        "endpoint": endpoint_name,
                        "status": "ambiguous",
                        "candidate_node_ids": candidate_ids,
                    }
                )
                continue
            distance, node_id, node = ranked[0]
            owning_ways = [
                way for way in nearby_ways if node_id in way.get("nodes", [])
            ]
            grade_issues = [
                (int(way["id"]), issue)
                for way in owning_ways
                for issue in [_connection_grade_issue(tags, way.get("tags", {}))]
                if issue
            ]
            if grade_issues:
                blocking.append(
                    f"{endpoint_name.capitalize()} endpoint cannot auto-connect to "
                    f"node {node_id}: {grade_issues[0][1]}"
                )
                continue
            snapped_refs[point_index] = node_id
            snapshot_nodes[node_id] = {
                "id": node_id,
                "version": int(node.get("version", 0)),
            }
            endpoint_snaps.append(
                {
                    "endpoint": endpoint_name,
                    "node_id": node_id,
                    "distance_m": round(distance, 2),
                    "kind": "existing_node",
                }
            )
            continue

        ranked_ways: List[Tuple[float, int, int, float, Point]] = []
        for way in nearby_ways:
            geometry = [
                (float(item["lat"]), float(item["lon"]))
                for item in way.get("geometry", [])
            ]
            if len(geometry) < 2:
                continue
            distance, segment_index, t, projected, _ = _nearest_on_polyline(
                points[point_index], geometry
            )
            if distance <= endpoint_snap_tolerance_m:
                ranked_ways.append(
                    (distance, int(way["id"]), segment_index, t, projected)
                )
        ranked_ways.sort(key=lambda item: (item[0], item[1]))
        if not ranked_ways:
            dangling_endpoints.append(
                {
                    "endpoint": endpoint_name,
                    "reason": (
                        "No reusable highway node or way was found within "
                        f"{endpoint_snap_tolerance_m:.1f}m"
                    ),
                }
            )
            continue
        if not connect_endpoints_to_ways:
            dangling_endpoints.append(
                {
                    "endpoint": endpoint_name,
                    "nearest_way_id": ranked_ways[0][1],
                    "distance_m": round(ranked_ways[0][0], 2),
                    "reason": "Endpoint-to-way connection planning was disabled",
                }
            )
            continue
        if (
            len(ranked_ways) > 1
            and ranked_ways[1][0] - ranked_ways[0][0] < ENDPOINT_WAY_AMBIGUITY_M
        ):
            candidate_ids = [item[1] for item in ranked_ways[:5]]
            blocking.append(
                f"{endpoint_name.capitalize()} endpoint is ambiguously close to "
                f"multiple highway ways: {candidate_ids}"
            )
            endpoint_way_connections.append(
                {
                    "endpoint": endpoint_name,
                    "status": "ambiguous",
                    "candidate_way_ids": candidate_ids,
                }
            )
            continue
        best = ranked_ways[0]
        pending_way_connections[point_index] = {
            "endpoint": endpoint_name,
            "way_id": best[1],
            "map_distance_m": best[0],
        }

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

    fetched_connection_ways: Dict[int, Dict[str, Any]] = {}
    verified_connections: Dict[int, Dict[str, Any]] = {}
    async with get_authenticated_client() as client:
        for node_id in list(snapshot_nodes):
            response = await client.get(f"{config.current_api_base_url}/node/{node_id}")
            if response.status_code != 200:
                raise ValueError(
                    f"Could not verify snapped endpoint node {node_id}: "
                    f"HTTP {response.status_code}"
                )
            root = parse_xml(response.text)
            node_element = root.find(".//node")
            if node_element is None or node_element.get("version") is None:
                raise ValueError(
                    f"Could not determine version for snapped endpoint node {node_id}"
                )
            snapshot_nodes[node_id]["version"] = int(node_element.get("version", "0"))
            authoritative_point = (
                float(node_element.get("lat", "0")),
                float(node_element.get("lon", "0")),
            )
            for point_index, snapped_node_id in snapped_refs.items():
                if snapped_node_id == node_id:
                    points[point_index] = authoritative_point

        connection_way_ids = sorted(
            {item["way_id"] for item in pending_way_connections.values()}
        )
        if connection_way_ids:
            fetched = await asyncio.gather(
                *(_fetch_way_full(client, way_id) for way_id in connection_way_ids)
            )
            fetched_connection_ways = {way["id"]: way for way in fetched}
        for point_index, pending in pending_way_connections.items():
            way = fetched_connection_ways[pending["way_id"]]
            grade_issue = _connection_grade_issue(tags, way.get("tags", {}))
            if grade_issue:
                blocking.append(
                    f"{pending['endpoint'].capitalize()} endpoint cannot auto-connect "
                    f"to way {way['id']}: {grade_issue}"
                )
                continue
            geometry = [
                (way["nodes"][node_id]["lat"], way["nodes"][node_id]["lon"])
                for node_id in way["node_ids"]
            ]
            distance, segment_index, t, projected, _ = _nearest_on_polyline(
                points[point_index], geometry
            )
            endpoint_name = pending["endpoint"]
            if distance > endpoint_snap_tolerance_m:
                blocking.append(
                    f"{endpoint_name.capitalize()} endpoint is now {distance:.1f}m "
                    f"from candidate way {way['id']}; create a fresh preview"
                )
                continue
            if t <= 1e-9 or t >= 1 - 1e-9:
                boundary_index = segment_index if t <= 1e-9 else segment_index + 1
                node_id = way["node_ids"][boundary_index]
                node = way["nodes"][node_id]
                snapped_refs[point_index] = node_id
                snapshot_nodes[node_id] = {"version": node["version"]}
                points[point_index] = (node["lat"], node["lon"])
                endpoint_snaps.append(
                    {
                        "endpoint": endpoint_name,
                        "node_id": node_id,
                        "distance_m": round(distance, 2),
                        "kind": "existing_way_boundary_node",
                        "way_id": way["id"],
                    }
                )
                continue
            points[point_index] = projected
            verified_connections[point_index] = {
                "endpoint": endpoint_name,
                "way_id": way["id"],
                "distance_m": distance,
                "segment_index": segment_index,
                "segment_fraction": t,
                "projected": projected,
            }
        max_way_nodes, server_max_changes = await _fetch_api_limits(client)

    create_nodes: List[Dict[str, Any]] = []
    refs: List[int] = []
    next_temp = -1
    for index, point in enumerate(points):
        if index in snapped_refs:
            refs.append(snapped_refs[index])
            continue
        refs.append(next_temp)
        create_nodes.append(
            {"id": next_temp, "lat": point[0], "lon": point[1], "tags": {}}
        )
        if index in verified_connections:
            connection = verified_connections[index]
            connection["new_node_id"] = next_temp
            endpoint_way_connections.append(
                {
                    "endpoint": connection["endpoint"],
                    "status": "planned",
                    "way_id": connection["way_id"],
                    "distance_m": round(connection["distance_m"], 2),
                    "new_node_id": next_temp,
                    "insert_after_node_id": fetched_connection_ways[
                        connection["way_id"]
                    ]["node_ids"][connection["segment_index"]],
                    "insert_before_node_id": fetched_connection_ways[
                        connection["way_id"]
                    ]["node_ids"][connection["segment_index"] + 1],
                    "coordinates": {
                        "lat": point[0],
                        "lon": point[1],
                    },
                }
            )
        next_temp -= 1

    created_by_id = {node["id"]: node for node in create_nodes}
    modify_ways: List[Dict[str, Any]] = []
    current_features: List[Dict[str, Any]] = []
    modified_features: List[Dict[str, Any]] = []
    insertions_by_way: Dict[int, List[Dict[str, Any]]] = {}
    for connection in verified_connections.values():
        if "new_node_id" in connection:
            insertions_by_way.setdefault(connection["way_id"], []).append(connection)
    for way_id, insertions in insertions_by_way.items():
        way = fetched_connection_ways[way_id]
        insertions_by_segment: Dict[int, List[Dict[str, Any]]] = {}
        for insertion in insertions:
            insertions_by_segment.setdefault(insertion["segment_index"], []).append(
                insertion
            )
        proposed_ids: List[int] = []
        for segment_index, node_id in enumerate(way["node_ids"][:-1]):
            proposed_ids.append(node_id)
            for insertion in sorted(
                insertions_by_segment.get(segment_index, []),
                key=lambda item: item["segment_fraction"],
            ):
                if proposed_ids[-1] != insertion["new_node_id"]:
                    proposed_ids.append(insertion["new_node_id"])
        proposed_ids.append(way["node_ids"][-1])
        modify_ways.append(
            {
                "id": way["id"],
                "version": way["version"],
                "node_ids": proposed_ids,
                "tags": way["tags"],
            }
        )
        current_coords = [
            (way["nodes"][node_id]["lat"], way["nodes"][node_id]["lon"])
            for node_id in way["node_ids"]
        ]
        proposed_coords = []
        for node_id in proposed_ids:
            node = created_by_id.get(node_id) or way["nodes"][node_id]
            proposed_coords.append((node["lat"], node["lon"]))
        current_features.append(
            _line_feature(current_coords, {"way_id": way_id, "state": "current"})
        )
        modified_features.append(
            _line_feature(proposed_coords, {"way_id": way_id, "state": "proposed"})
        )

    planned_connection_ids = sorted(
        {
            int(connection["way_id"])
            for connection in endpoint_way_connections
            if connection.get("status") == "planned"
        }
    )
    if planned_connection_ids:
        warnings.append(
            "Endpoint connection will insert a shared node into existing highway "
            f"ways: {planned_connection_ids}. Review the proposed topology."
        )

    if len(refs) > max_way_nodes:
        blocking.append(
            f"Proposed way has {len(refs)} nodes; API maximum is {max_way_nodes}"
        )
    for way in modify_ways:
        if len(way["node_ids"]) > max_way_nodes:
            blocking.append(
                f"Way {way['id']} would have {len(way['node_ids'])} nodes; "
                f"API maximum is {max_way_nodes}"
            )
    operation_count = len(create_nodes) + 1 + len(modify_ways)
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
        "modify_ways": modify_ways,
        "delete_nodes": [],
        "snapshot_ways": {
            str(way["id"]): {
                "version": way["version"],
                "node_ids": way["node_ids"],
                "tags": way["tags"],
            }
            for way in fetched_connection_ways.values()
            if way["id"] in insertions_by_way
        },
        "snapshot_nodes": snapshot_nodes,
        "context_points": points,
        "context_radius_m": max(30.0, endpoint_snap_tolerance_m),
        "context_highways": _highway_context_snapshot(nearby_ways),
        "endpoint_snaps": endpoint_snaps,
        "endpoint_way_connections": endpoint_way_connections,
        "dangling_endpoints": dangling_endpoints,
        "preserved_nodes": list(snapped_refs.values()),
        "warnings": warnings,
        "blocking_issues": blocking,
        "summary": {
            "new_nodes": len(create_nodes),
            "new_ways": 1,
            "modified_ways": len(modify_ways),
            "conditional_node_deletions": 0,
            "element_operations": operation_count,
        },
    }
    proposal = _store_proposal(payload, verified_osm_uid)
    return _proposal_result(
        proposal,
        _feature_collection(current_features),
        _feature_collection(
            modified_features + [_line_feature(points, {"action": "create"})]
        ),
    )


async def _preview_update(
    track_hash: str,
    segment: TrackSegment,
    target_way_ids: Sequence[int],
    comment: str,
    source: str,
    simplify_tolerance_m: float,
    max_alignment_distance_m: float,
    verified_osm_uid: int,
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
    proposal = _store_proposal(payload, verified_osm_uid)
    return _proposal_result(
        proposal,
        _feature_collection(current_features),
        _feature_collection(proposed_features),
    )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def preview_track_road_edit(
    action: str,
    changeset_comment: str,
    changeset_source: str,
    segment_id: Optional[str] = None,
    gpx_xml: Optional[str] = None,
    gpx_path: Optional[str] = None,
    target_way_ids: Optional[List[int]] = None,
    tags: Optional[Dict[str, str]] = None,
    simplify_tolerance_m: float = DEFAULT_SIMPLIFY_TOLERANCE_M,
    endpoint_snap_tolerance_m: float = DEFAULT_ENDPOINT_SNAP_M,
    connect_endpoints_to_ways: bool = True,
    max_alignment_distance_m: float = DEFAULT_MAX_ALIGNMENT_M,
    selection_id: Optional[str] = None,
    evidence_kind: str = "survey_gpx",
    evidence_provider: Optional[str] = None,
    evidence_observed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a non-writing GeoJSON and element diff preview for a road edit.
    Requires OAuth with write_api: the stored proposal is bound to the verified
    OSM account and API target before review. Read-only means no OSM upload,
    not anonymous access. For an OAuth-free geometry view use
    analyze_gpx_track, create_track_selection and its preview_uri instead.
    Applying this proposal still requires a separate digest-bound confirmation.
    """
    try:
        action = action.lower().strip()
        if action not in {"create", "update"}:
            raise ValueError("action must be 'create' or 'update'")
        if not changeset_comment.strip():
            raise ValueError("changeset_comment must not be empty")
        if not changeset_source.strip():
            raise ValueError("changeset_source must not be empty")
        source_lower = changeset_source.lower()
        if "yandex" in source_lower or "google" in source_lower:
            raise ValueError(
                "Yandex/Google map geometry is not permitted evidence for OSM tracing"
            )
        if evidence_kind not in {"survey_gpx", "local_knowledge", "permitted_imagery"}:
            raise ValueError("Unsupported evidence_kind")
        provider = (evidence_provider or "").strip()
        if any(name in provider.casefold() for name in ("yandex", "google")):
            raise ValueError(
                "Yandex/Google map geometry is not permitted evidence for OSM tracing"
            )
        if evidence_kind == "permitted_imagery":
            if not provider:
                raise ValueError(
                    "permitted_imagery requires an explicit evidence_provider"
                )
            if provider.casefold() not in config.permitted_imagery_sources:
                raise ValueError(
                    "Imagery provider is not in OSM_PERMITTED_IMAGERY_SOURCES"
                )
        if not 0 <= simplify_tolerance_m <= 100:
            raise ValueError("simplify_tolerance_m must be between 0 and 100")
        if not 0 <= endpoint_snap_tolerance_m <= 100:
            raise ValueError("endpoint_snap_tolerance_m must be between 0 and 100")
        if not 1 <= max_alignment_distance_m <= 100:
            raise ValueError("max_alignment_distance_m must be between 1 and 100")
        digest, segment = _resolve_edit_segment(
            selection_id, segment_id, gpx_xml, gpx_path
        )
        _require_continuous_segment(segment)
        async with get_authenticated_client() as client:
            try:
                identity = await verify_write_identity(client)
            except PermissionError as exc:
                return _failure(
                    type(exc).__name__,
                    "Road-edit preview requires OAuth identity and write_api permission; no OSM edit was sent",
                    detail=describe_exception(exc),
                    authentication_required=True,
                    next_steps=[
                        "Authenticate for the configured API target, then rebuild the proposal",
                        "For an OAuth-free selection preview, use create_track_selection and its preview_uri",
                    ],
                )
        verified_osm_uid = int(identity["user_id"])
        if action == "create":
            if target_way_ids:
                raise ValueError("target_way_ids are not allowed for action=create")
            result = await _preview_create(
                digest,
                segment,
                tags or {},
                changeset_comment.strip(),
                changeset_source.strip(),
                simplify_tolerance_m,
                endpoint_snap_tolerance_m,
                connect_endpoints_to_ways,
                verified_osm_uid,
            )
        else:
            if tags:
                raise ValueError("Track updates preserve existing way tags; omit tags")
            result = await _preview_update(
                digest,
                segment,
                target_way_ids or [],
                changeset_comment.strip(),
                changeset_source.strip(),
                simplify_tolerance_m,
                max_alignment_distance_m,
                verified_osm_uid,
            )
        if result.get("data"):
            result["data"]["selection_id"] = selection_id
            proposal_id = result["data"].get("proposal_id")
            proposal = _PROPOSALS.get(proposal_id)
            if proposal:
                proposal.payload["selection_id"] = selection_id
                proposal.payload["evidence"] = {
                    "kind": evidence_kind,
                    "provider": provider or None,
                    "observed_at": evidence_observed_at,
                    "license_status": (
                        "user_survey"
                        if evidence_kind == "survey_gpx"
                        else "must_be_reviewed"
                    ),
                }
                _refresh_proposal_digest(proposal)
                result["data"]["proposal_digest"] = proposal.digest
        return result
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
    context_points = payload.get("context_points")
    context_highways = payload.get("context_highways")
    if context_points is not None and context_highways is not None:
        current_ways, _ = await _nearby_highways(
            [tuple(point) for point in context_points],
            float(payload.get("context_radius_m", 30.0)),
        )
        if _highway_context_snapshot(current_ways) != context_highways:
            raise ValueError(
                "Highway geometry in the affected area changed after preview; "
                "create a fresh proposal"
            )
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


async def _validate_supplied_changeset(
    client: Any, changeset_id: int, osm_uid: int
) -> None:
    response = await client.get(
        f"{config.current_api_base_url}/changeset/{changeset_id}"
    )
    if response.status_code != 200:
        raise ValueError(
            f"Supplied changeset {changeset_id} is not accessible or does not exist"
        )
    root = parse_xml(response.text)
    element = root.find(".//changeset")
    if element is None:
        raise ValueError("OSM changeset response did not contain a changeset")
    if element.get("open") != "true":
        raise ValueError(f"Supplied changeset {changeset_id} is closed")
    owner = element.get("uid") or element.get("user_id")
    if owner is None or int(owner) != osm_uid:
        raise ValueError(
            f"Supplied changeset {changeset_id} belongs to a different OSM account"
        )


async def _create_owned_changeset(client: Any, payload: Dict[str, Any]) -> int:
    root = ET.Element("osm")
    changeset = ET.SubElement(root, "changeset")
    for key, value in {
        "comment": payload["changeset_comment"],
        "source": payload["changeset_source"],
        "created_by": config.default_changeset_created_by,
    }.items():
        ET.SubElement(changeset, "tag", {"k": key, "v": str(value)})
    response = await client.put(
        f"{config.current_api_base_url}/changeset/create",
        content=ET.tostring(root, encoding="unicode"),
        headers={"Content-Type": "text/xml"},
    )
    if response.status_code != 200:
        raise RuntimeError(
            "OSM changeset creation failed with HTTP "
            f"{response.status_code}: {response.text}"
        )
    return int(response.text.strip())


async def _close_owned_changeset(client: Any, changeset_id: int) -> bool:
    response = await client.put(
        f"{config.current_api_base_url}/changeset/{changeset_id}/close"
    )
    return int(response.status_code) == 200


async def _verify_diff_results(
    client: Any, diff_results: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    verified: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for item in diff_results:
        element_type = item["type"]
        element_id = int(item["new_id"])
        expected_version = int(item["new_version"])
        if element_id <= 0 or element_type not in {"node", "way", "relation"}:
            continue
        actual_version: Optional[int] = None
        verification_error: Optional[str] = None
        try:
            response = await client.get(
                f"{config.current_api_base_url}/{element_type}/{element_id}"
            )
            if response.status_code == 200:
                root = parse_xml(response.text)
                element = root.find(f".//{element_type}")
                if element is not None:
                    actual_version = int(element.get("version", "0"))
            else:
                verification_error = f"HTTP {response.status_code}"
        except Exception as exc:
            verification_error = describe_exception(exc)
        record = {
            **item,
            "url": f"{config.current_web_base_url}/{element_type}/{element_id}",
            "actual_version": actual_version,
            "verification_error": verification_error,
        }
        if actual_version == expected_version:
            verified.append(record)
        else:
            failures.append(record)
    return {
        "status": "verified" if not failures else "verification_incomplete",
        "verified": verified,
        "failures": failures,
    }


async def _inspect_changeset_download(changeset_id: int) -> Dict[str, Any]:
    """Inspect an ambiguous upload outcome without retrying the write."""
    try:
        async with get_authenticated_client() as client:
            response = await client.get(
                f"{config.current_api_base_url}/changeset/{changeset_id}/download"
            )
        if response.status_code != 200:
            return {
                "status": "unavailable",
                "http_status": response.status_code,
            }
        root = parse_xml(response.text)
        elements: List[Dict[str, Any]] = []
        for section in root:
            operation = _local_name(section.tag)
            for element in section:
                element_type = _local_name(element.tag)
                if element_type not in {"node", "way", "relation"}:
                    continue
                element_id = int(element.get("id", "0"))
                elements.append(
                    {
                        "operation": operation,
                        "type": element_type,
                        "id": element_id,
                        "version": int(element.get("version", "0")),
                        "url": (
                            f"{config.current_web_base_url}/{element_type}/{element_id}"
                        ),
                    }
                )
        return {
            "status": "changeset_contains_elements" if elements else "empty",
            "elements": elements,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": describe_exception(exc),
        }


async def _apply_osm_edit_internal(
    proposal_id: str,
    proposal_digest: str,
    changeset_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Claim, upload, reconcile and persist a proposal exactly once."""
    proposal = _get_proposal(proposal_id)
    if proposal is None:
        return _failure(
            "Unknown or expired proposal",
            "Create a fresh preview before applying the road edit",
        )
    if proposal.digest != proposal_digest:
        return _failure(
            "Proposal digest mismatch",
            "The reviewed proposal changed; review a fresh preview",
        )
    payload = proposal.payload
    if payload.get("blocking_issues"):
        return _failure(
            "Proposal is blocked",
            "Resolve all blocking issues and create a fresh preview",
            blocking_issues=payload["blocking_issues"],
        )
    if not load_oauth_token():
        return _failure(
            "Authentication required",
            "OSM edits require OAuth with the write_api scope",
        )

    owned_changeset = changeset_id is None
    active_changeset_id = changeset_id
    upload_started = False
    upload_confirmed = False
    try:
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
            osm_uid = int(identity["user_id"])
            claimed = _PROPOSAL_STORE.claim(
                proposal_id,
                proposal_digest,
                config.current_api_base_url,
                osm_uid,
            )
            if claimed.status == "APPLIED" and claimed.receipt:
                return {
                    "success": True,
                    "data": claimed.receipt,
                    "message": "Proposal was already applied; returning its receipt",
                }
            await _validate_proposal_versions(client, payload)
            if active_changeset_id is not None:
                await _validate_supplied_changeset(
                    client, int(active_changeset_id), osm_uid
                )
            if active_changeset_id is None:
                active_changeset_id = await _create_owned_changeset(client, payload)
            _PROPOSAL_STORE.set_changeset_id(proposal_id, int(active_changeset_id))

            osm_change = _build_osm_change(payload, int(active_changeset_id))
            upload_started = True
            response = await client.post(
                f"{config.current_api_base_url}/changeset/{active_changeset_id}/upload",
                content=osm_change,
                headers={"Content-Type": "text/xml"},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    "OSM diff upload failed with HTTP "
                    f"{response.status_code}: {response.text}"
                )
            upload_confirmed = True
            diff_results = _parse_diff_result(response.text)
            verification = await _verify_diff_results(client, diff_results)
            changeset_closed = (
                await _close_owned_changeset(client, int(active_changeset_id))
                if owned_changeset
                else False
            )
        receipt = {
            "proposal_id": proposal_id,
            "proposal_digest": proposal_digest,
            "api_target": config.current_api_base_url,
            "osm_uid": osm_uid,
            "changeset_id": int(active_changeset_id),
            "changeset_url": (
                f"{config.current_web_base_url}/changeset/{active_changeset_id}"
            ),
            "diff_results": diff_results,
            "verification": verification,
            "changeset_closed": changeset_closed,
            "summary": payload["summary"],
        }
        _PROPOSAL_STORE.finish(proposal_id, "APPLIED", receipt=receipt)
        proposal.status = "APPLIED"
        return {
            "success": True,
            "data": receipt,
            "message": "OSM edit uploaded successfully",
        }
    except ProposalStoreError as exc:
        return _failure(
            type(exc).__name__,
            "Proposal could not be reserved for upload",
            detail=str(exc),
        )
    except Exception as exc:
        is_ambiguous_upload = upload_confirmed or (
            upload_started and isinstance(exc, httpx.TransportError)
        )
        status = "RECONCILE_REQUIRED" if is_ambiguous_upload else "FAILED"
        reconciliation: Optional[Dict[str, Any]] = None
        if is_ambiguous_upload and active_changeset_id is not None:
            reconciliation = await _inspect_changeset_download(int(active_changeset_id))
        try:
            _PROPOSAL_STORE.finish(
                proposal_id,
                status,
                receipt=(
                    {
                        "proposal_id": proposal_id,
                        "proposal_digest": proposal_digest,
                        "changeset_id": active_changeset_id,
                        "changeset_url": (
                            f"{config.current_web_base_url}/changeset/"
                            f"{active_changeset_id}"
                        ),
                        "reconciliation": reconciliation,
                    }
                    if reconciliation
                    else None
                ),
                error=describe_exception(exc),
            )
        except Exception:
            pass
        if owned_changeset and active_changeset_id is not None:
            try:
                await close_changeset(int(active_changeset_id))
            except Exception:
                pass
        return _failure(
            type(exc).__name__,
            (
                "Upload outcome is unknown; do not retry. Reconcile the changeset first"
                if is_ambiguous_upload
                else "Failed to apply OSM edit; create a fresh proposal before retrying"
            ),
            detail=describe_exception(exc),
            changeset_id=active_changeset_id,
            proposal_status=status,
            reconciliation=reconciliation,
        )


async def _request_host_confirmation(
    proposal: Proposal, context: Context
) -> Optional[Dict[str, Any]]:
    """Request a separate host confirmation bound to one exact proposal."""
    try:
        _PROPOSAL_STORE.mark_awaiting_approval(proposal.proposal_id)
    except ProposalStoreError as exc:
        return _failure(
            type(exc).__name__,
            "Proposal is not available for confirmation",
            detail=str(exc),
        )
    environment = config.api_environment.upper()
    try:
        confirmation = await context.elicit(
            (
                f"{environment} OSM WRITE. "
                f"Review {proposal.payload.get('summary', {})}. "
                f"API: {proposal.api_target}. "
                f"OSM UID: {proposal.osm_uid}. "
                f"Proposal SHA-256: {proposal.digest}. "
                "Confirm only if the map preview and exact element "
                "operations are correct."
            ),
            ApplyConfirmation,
        )
    except Exception as exc:
        return _failure(
            "Host confirmation unavailable",
            "This MCP client cannot safely approve the requested write",
            detail=describe_exception(exc),
        )
    if (
        confirmation.action != "accept"
        or confirmation.data is None
        or confirmation.data.confirm is not True
        or confirmation.data.proposal_digest != proposal.digest
    ):
        return _failure(
            "Confirmation declined",
            "The host did not approve this exact proposal digest",
        )
    return None


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def apply_osm_edit(
    proposal_id: str,
    proposal_digest: str,
    context: Context,
    changeset_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Apply a reviewed proposal after a separate client-host confirmation."""
    proposal = _get_proposal(proposal_id)
    if proposal is None:
        return _failure(
            "Unknown or expired proposal",
            "Create and review a fresh proposal",
        )
    if proposal.digest != proposal_digest:
        return _failure(
            "Proposal digest mismatch",
            "The exact reviewed digest is required",
        )
    if proposal.status == "APPLIED":
        return await _apply_osm_edit_internal(
            proposal_id, proposal_digest, changeset_id
        )
    if config.osm_require_host_confirmation or not config.is_development_api:
        confirmation_failure = await _request_host_confirmation(proposal, context)
        if confirmation_failure is not None:
            return confirmation_failure
    return await _apply_osm_edit_internal(proposal_id, proposal_digest, changeset_id)


async def apply_track_road_edit(
    proposal_id: str,
    proposal_digest: str,
    confirm: bool,
    context: Context,
    changeset_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Apply an exact dev-API digest after separate host confirmation."""
    if not config.is_development_api:
        return _failure(
            "Development API required",
            "Non-development targets must use apply_osm_edit with MCP elicitation",
        )
    if confirm is not True:
        return _failure(
            "Confirmation required",
            "Review the complete preview before requesting apply",
        )
    proposal = _get_proposal(proposal_id)
    if proposal is None:
        return _failure(
            "Unknown or expired proposal",
            "Create a fresh preview before applying the road edit",
        )
    if proposal.digest != proposal_digest:
        return _failure(
            "Proposal digest mismatch",
            "The exact reviewed digest is required",
        )
    if proposal.status != "APPLIED":
        confirmation_failure = await _request_host_confirmation(proposal, context)
        if confirmation_failure is not None:
            return confirmation_failure
    return await _apply_osm_edit_internal(proposal_id, proposal_digest, changeset_id)


if config.is_development_api:
    profile_tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=True,
        )
    )(apply_track_road_edit)


__all__ = [
    "analyze_gpx_track",
    "apply_osm_edit",
    "apply_track_road_edit",
    "create_track_selection",
    "match_track_selection",
    "preview_track_road_edit",
    "suggest_track_road_candidates",
]
