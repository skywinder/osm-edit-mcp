"""Find mapped stops along a directed survey trace without assuming service."""

import asyncio
import math
from collections import defaultdict
from typing import Annotated, Any, Literal, Optional, Sequence

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import Field, StrictInt

from .app import profile_tool
from .config import DEFAULT_OVERPASS_URL, config
from .discovery_errors import failure
from .http_client import get_public_client
from .overpass import overpass
from .place_features import ATTRIBUTION
from .track_tools import Point, _expanded_bbox, _haversine_m, _resolve_track_selection
from .transit_data import element_tags
from .transit_geometry import Edge, _edges, _role
from .transit_match import MAX_GAP_M, MAX_PREVIEW_POINTS, Provider, SurveyPoint

MAX_NODES = 3000
MAX_VISITS = 3000
MAX_PROJECTIONS = 3_000_000
MAX_WINDOWS = 80
WINDOW_LENGTH_M = 1300.0
Side = Literal["right", "left"]


# Keep the matcher’s part numbers even when an intervening survey leg had no match.
Parts = dict[int, Sequence[Point]]


def _validate_line(points: Sequence[Point]) -> None:
    if len(points) < 2 or all(p == points[0] for p in points):
        raise ValueError("Provide at least two distinct coordinates per line")
    if any(not (-90 < lat < 90 and -180 <= lon <= 180) for lat, lon in points):
        raise ValueError("Trace points must be finite and inside map bounds")
    if any(abs(a[1] - b[1]) > 180 for a, b in zip(points, points[1:])):
        raise ValueError("Split the trace at the antimeridian")


def _path_parts(points: Sequence[Point]) -> tuple[Parts, list[dict[str, Any]]]:
    """Break at survey gaps. Zero-length samples retain their original indices."""
    index = 0
    parts: Parts = {}
    gaps: list[dict[str, Any]] = []

    def append_part(line: Sequence[Point]) -> None:
        if any(p != line[0] for p in line[1:]):
            parts[len(parts)] = line

    for i, (a, b) in enumerate(zip(points, points[1:])):
        distance = _haversine_m(a, b)
        if distance > MAX_GAP_M["trace"]:
            append_part(points[index : i + 1])
            gaps.append(
                {
                    "start_point_index": i,
                    "end_point_index": i + 1,
                    "distance_m": round(distance, 1),
                    "reason": "survey_points_over_500m_apart",
                }
            )
            index = i + 1
    append_part(points[index:])
    return parts, gaps


def _matched_parts(collection: dict[str, Any]) -> tuple[Parts, list[dict[str, Any]]]:
    features = collection.get("features")
    if collection.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError(
            "Provide matched_geojson as a FeatureCollection of LineStrings"
        )
    source = collection.get("source", {})
    if not isinstance(source, dict) or any(
        key in source and source[key] != expected
        for key, expected in (
            ("environment", config.api_environment),
            ("api_target", config.current_api_base_url),
        )
    ):
        raise ValueError(
            "Matched GeoJSON source differs from the configured OSM API target"
        )

    parts: Parts = {}
    gaps: list[dict[str, Any]] = []
    size = 0
    previous = -1
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Expected a GeoJSON Feature for each connected part")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            raise ValueError("Matched features must have LineString geometry")
        properties = feature.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError("Expected an object for matched feature properties")
        part = properties.get("part", index) if properties is not None else index
        if type(part) is not int or part <= previous:
            raise ValueError(
                "Matched part numbers must be nonnegative and strictly increasing"
            )
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ValueError("Expected an array of [longitude, latitude] coordinates")
        size += len(coordinates)
        if size > MAX_PREVIEW_POINTS:
            raise ValueError(
                f"Matched GeoJSON exceeds {MAX_PREVIEW_POINTS} coordinates"
            )
        line: list[Point] = []
        for position in coordinates:
            if (
                not isinstance(position, (list, tuple))
                or len(position) != 2
                or any(type(value) not in (int, float) for value in position)
            ):
                raise ValueError("Expected numeric [longitude, latitude] pairs")
            line.append((position[1], position[0]))
        _validate_line(line)
        if previous >= 0:
            gaps.append(
                {
                    "after_part": previous,
                    "before_part": part,
                    "distance_m": round(_haversine_m(parts[previous][-1], line[0]), 1),
                    "reason": "separate_matched_parts",
                }
            )
        parts[part] = line
        previous = part
    return parts, gaps


def _corridor_windows(parts: Parts) -> list[list[Point]]:
    """Cover each line separately, including long connected OSM edges."""
    windows: list[list[Point]] = []
    for points in parts.values():
        window = [points[0]]
        for start, end in zip(points, points[1:]):
            # Split long edges for the bbox query only. Projection uses the OSM geometry.
            divisions = max(1, math.ceil(_haversine_m(start, end) / WINDOW_LENGTH_M))
            for step in range(1, divisions + 1):
                point = (
                    end
                    if step == divisions
                    else (
                        start[0] + (end[0] - start[0]) * step / divisions,
                        start[1] + (end[1] - start[1]) * step / divisions,
                    )
                )
                if len(window) > 1 and _haversine_m(window[0], point) > WINDOW_LENGTH_M:
                    windows.append(window)
                    window = [window[-1]]
                if len(windows) >= MAX_WINDOWS:
                    raise ValueError(
                        f"Select a shorter trace (at most {MAX_WINDOWS} map windows)"
                    )
                window.append(point)
        windows.append(window)
    return windows


async def _stop_nodes(
    parts: Parts, radius: float, provider: Provider
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    windows = _corridor_windows(parts)
    public_map = (
        config.api_environment == "production"
        and overpass.endpoint == DEFAULT_OVERPASS_URL
    )
    if provider == "overpass" and not public_map:
        raise ValueError(
            "Public Overpass requires the matching production OSM API target"
        )
    boxes = []
    for chunk in windows:
        south, west, north, east = _expanded_bbox(chunk, radius * 1.02)
        if south < -90 or north > 90 or west < -180 or east > 180:
            raise ValueError("Stop corridor crosses a pole or the antimeridian")
        boxes.append(tuple(round(x, 7) for x in (south, west, north, east)))
    boxes = list(dict.fromkeys(boxes))
    source: dict[str, Any] = {
        "api_target": config.current_api_base_url,
        "environment": config.api_environment,
        "attribution": ATTRIBUTION,
        "map_windows": len(boxes),
    }
    if not boxes:
        return [], {**source, "provider": "no covered survey legs"}
    if public_map and provider != "editing_api":
        statements = []
        for box in boxes:
            bounds = ",".join(map(str, box))
            statements.extend(
                [
                    f'node["public_transport"~"^(platform|stop_position)$"]({bounds});',
                    f'node["highway"~"^(bus_stop|platform)$"]({bounds});',
                ]
            )
        query = (
            f'[out:json][timeout:25];({"".join(statements)});out body {MAX_NODES+1};'
        )
        response = await overpass.execute(query)
        nodes = response["elements"]
        source.update(
            provider="Overpass",
            data_timestamp=response.get("osm3s", {}).get("timestamp_osm_base"),
        )
    else:
        unique: dict[int, dict[str, Any]] = {}
        async with get_public_client() as client:

            async def fetch(box: tuple[float, ...]) -> list[dict[str, Any]]:
                south, west, north, east = box
                response = await client.get(
                    f"{config.current_api_base_url}/map",
                    params={"bbox": f"{west},{south},{east},{north}"},
                )
                response.raise_for_status()
                root = parse_xml(response.text)
                if root.tag != "osm":
                    raise ValueError("Incomplete OSM map response")
                results = []
                for n in root.findall("node"):
                    if n.find("tag") is None or n.get("visible") == "false":
                        continue
                    item = {
                        "id": int(n.attrib["id"]),
                        "lat": float(n.attrib["lat"]),
                        "lon": float(n.attrib["lon"]),
                        "tags": element_tags(n),
                    }
                    if _role(item):
                        results.append(item)
                return results

            for offset in range(0, len(boxes), 2):
                for group in await asyncio.gather(
                    *(fetch(box) for box in boxes[offset : offset + 2])
                ):
                    unique.update((item["id"], item) for item in group)
                if len(unique) > MAX_NODES:
                    raise ValueError(
                        "Too many mapped stops in these windows; select a shorter trace"
                    )
        nodes = list(unique.values())
        source["provider"] = "OSM editing API"
    if len(nodes) > MAX_NODES:
        raise ValueError(
            "Too many mapped stops in these windows; select a shorter trace"
        )
    return nodes, source


def _visits(
    node: dict[str, Any], role: str, edges: list[Edge], side: Side, radius: float
) -> list[dict[str, Any]]:
    point = (node["lat"], node["lon"])
    projections = [e.projection(point) for e in edges]
    visits: list[dict[str, Any]] = []
    for i, (distance, along, cross, longitudinal) in enumerate(projections):
        if distance > radius:
            continue
        if i and projections[i - 1][0] < distance - 0.01:
            continue
        if i + 1 < len(edges) and projections[i + 1][0] < distance - 0.01:
            continue
        reasons = []
        edge = edges[i]
        along_edge = along - edge.along
        # A projection clamped to an endpoint can be longitudinally far from
        # the observed trace, even when the lateral offset has a clear sign.
        if (i == 0 and longitudinal < -5) or (
            i == len(edges) - 1 and longitudinal > edge.length + 5
        ):
            reasons.append("beyond_trace_endpoint")
        for neighbor, to_vertex in (
            (i - 1, along_edge),
            (i + 1, edge.length - along_edge),
        ):
            if 0 <= neighbor < len(edges) and to_vertex <= max(5, distance):
                other = edges[neighbor]
                dot = (edge.east * other.east + edge.north * other.north) / (
                    edge.length * other.length
                )
                if dot < 0.71:
                    reasons.append("near_sharp_turn")
                    break
        lateral = cross if side == "left" else -cross
        if role == "stop":
            # A stop_position on the centreline can serve one or both ways.
            # Node direction is relative to its OSM way, not an arbitrary trace.
            reasons.append("stop_position_requires_direction_check")
        elif abs(lateral) < 1:
            reasons.append("boarding_side_unclear")
        status = (
            "ambiguous" if reasons else ("candidate" if lateral > 0 else "opposite")
        )
        visit = {
            "along_m": round(along, 2),
            "distance_m": round(distance, 2),
            "status": status,
            "reasons": reasons,
        }
        # Equal projections at a shared trace vertex describe one visit.
        if visits and abs(visits[-1]["along_m"] - along) <= 0.5:
            prior = visits[-1]
            if prior["status"] != status:
                prior["status"] = "ambiguous"
                prior["reasons"] = sorted(
                    set([*prior["reasons"], *reasons, "ambiguous_boarding_side"])
                )
            elif distance < prior["distance_m"]:
                visits[-1] = visit
        else:
            visits.append(visit)
    return visits


def _analyze_stops(
    parts: Parts,
    gaps: list[dict[str, Any]],
    nodes: Sequence[dict[str, Any]],
    side: Side,
    radius: float,
    excluded: set[int],
) -> dict[str, Any]:
    edge_count = sum(a != b for line in parts.values() for a, b in zip(line, line[1:]))
    if edge_count * len(nodes) > MAX_PROJECTIONS:
        raise ValueError(
            "Too many stop/segment projections; select a shorter trace or smaller radius"
        )
    groups: dict[str, list[dict[str, Any]]] = {
        "candidate": [],
        "ambiguous": [],
        "opposite": [],
        "excluded": [],
    }
    same_names: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    distance_before = 0.0
    visits_count = 0
    for part, line in parts.items():
        positions = {i: {"lat": p[0], "lon": p[1]} for i, p in enumerate(line)}
        edges, _, _ = _edges(list(positions), positions, ["forward"] * (len(line) - 1))
        for node in nodes:
            role = _role(node)
            if role is None:
                continue
            for visit in _visits(node, role, edges, side, radius):
                visits_count += 1
                if visits_count > MAX_VISITS:
                    raise ValueError("Too many stop visits; select a shorter trace")
                name = node.get("tags", {}).get("name", "")
                row = {
                    **visit,
                    "node_id": node["id"],
                    "role": role,
                    "name": name,
                    "lat": node["lat"],
                    "lon": node["lon"],
                    "part": part,
                    "along_m": round(distance_before + visit["along_m"], 2),
                    "osm_url": f"{config.current_web_base_url}/node/{node['id']}",
                    "excluded": node["id"] in excluded,
                }
                groups["excluded" if row["excluded"] else row["status"]].append(row)
                if role == "platform" and name:
                    same_names[part, name.casefold().strip()].append(row)
        distance_before += edges[-1].along + edges[-1].length
    for namesakes in same_names.values():
        for item in namesakes:
            if item["status"] == "ambiguous":
                continue
            opposite_ids = {
                v["node_id"]
                for v in namesakes
                if v["node_id"] != item["node_id"]
                and {v["status"], item["status"]} == {"candidate", "opposite"}
                and abs(v["along_m"] - item["along_m"]) <= 150
            }
            if opposite_ids:
                item["nearby_same_name_opposite_node_ids"] = sorted(opposite_ids)
    for group in groups.values():
        group.sort(
            key=lambda row: (
                row["part"],
                row["along_m"],
                row["distance_m"],
                row["node_id"],
            )
        )
    return {
        "candidates": groups["candidate"],
        "ambiguous": groups["ambiguous"],
        "opposite": groups["opposite"],
        "excluded": groups["excluded"],
        "excluded_node_ids": sorted(excluded),
        "gaps": gaps,
        "covered_distance_m": round(distance_before, 2),
        "part_count": len(parts),
        "driving_side": side,
        "service_verified": False,
        "radius_m": radius,
    }


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def suggest_bus_route_stops(
    points: Optional[
        Annotated[list[SurveyPoint], Field(min_length=2, max_length=5000)]
    ] = None,
    selection_id: Optional[str] = None,
    driving_side: Side = "right",
    radius_m: Annotated[float, Field(ge=1, le=100)] = 35.0,
    excluded_node_ids: Optional[
        Annotated[list[Annotated[StrictInt, Field(gt=0)]], Field(max_length=250)]
    ] = None,
    provider: Provider = "auto",
    matched_geojson: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Find existing stop nodes along one directed trace, with local names and OSM IDs.
    Supply exactly one of ordered lat/lon points, a GPX selection_id, or the full
    matched_geojson FeatureCollection from suggest_bus_route_ways. Each matched
    LineString is searched in travel order and retains its part number. along_m
    sums covered distance, omitting breaks between parts and raw survey gaps over
    500 m. Review service, opposite-side platforms, ambiguous positions and explicit
    exclusions. Only bounding boxes are sent to the map provider. Read-only.
    """
    try:
        if sum(x is not None for x in (points, selection_id, matched_geojson)) != 1:
            raise ValueError(
                "Provide exactly one of points, selection_id or matched_geojson"
            )
        if matched_geojson is not None:
            parts, gaps = _matched_parts(matched_geojson)
        else:
            trace = (
                _resolve_track_selection(selection_id).points
                if selection_id is not None
                else tuple((p.lat, p.lon) for p in points or [])
            )
            if not 2 <= len(trace) <= 5000:
                raise ValueError("Provide 2–5000 survey points describing movement")
            _validate_line(trace)
            parts, gaps = _path_parts(trace)
        if (
            not 1 <= radius_m <= 100
            or driving_side not in {"right", "left"}
            or provider not in {"auto", "overpass", "editing_api"}
        ):
            raise ValueError(
                "Choose a supported driving side, provider and radius between 1 and 100 m"
            )
        exclusions = excluded_node_ids or []
        if len(exclusions) > 250 or any(
            type(i) is not int or i <= 0 for i in exclusions
        ):
            raise ValueError("Provide at most 250 positive OSM node IDs for exclusion")
        nodes, source = await _stop_nodes(parts, radius_m, provider)
        data = _analyze_stops(
            parts, gaps, nodes, driving_side, radius_m, set(exclusions)
        )
        return {
            "success": True,
            "data": {**data, "selection_id": selection_id, "source": source},
        }
    except Exception as exc:
        return failure(exc, "Could not discover mapped stops along the bus trace")
