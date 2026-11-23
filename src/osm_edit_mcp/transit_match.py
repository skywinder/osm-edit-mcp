"""Read-only, directional bus trace matching on existing OSM highway segments."""

import heapq
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import accumulate
from typing import Annotated, Any, Literal, Optional, Sequence

from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .app import profile_tool
from .config import DEFAULT_OVERPASS_URL, config
from .discovery_errors import failure
from .overpass import overpass
from .place_features import ATTRIBUTION
from .track_tools import (
    Point,
    _expanded_bbox,
    _haversine_m,
    _nearby_highways,
    _resolve_track_selection,
    _xy_m,
)
from .transit_geometry import _directions

SNAP_RADIUS_M = 35.0
GRID_M = 50.0
MAX_WAYS = 6500
MAX_GEOMETRY_POINTS = 150000
MAX_PREVIEW_POINTS = 4000
MAX_PREVIEW_BYTES = 128 * 1024
InputKind = Literal["trace", "waypoints"]
Provider = Literal["auto", "overpass", "editing_api"]
MAX_GAP_M: dict[InputKind, float] = {"trace": 500.0, "waypoints": 2000.0}


class SurveyPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@dataclass(frozen=True)
class Segment:
    way_id: int
    a: int
    b: int
    xy_a: Point
    xy_b: Point
    length: float
    start: float
    end: float
    forward: bool
    backward: bool

    def xy(self, t: float) -> Point:
        return (
            self.xy_a[0] + t * (self.xy_b[0] - self.xy_a[0]),
            self.xy_a[1] + t * (self.xy_b[1] - self.xy_a[1]),
        )

    def node_at(self, t: float) -> Optional[int]:
        if t == 0:
            return self.a
        if t == 1:
            return self.b
        return None

    def fraction(self, t: float) -> float:
        return self.start + (self.end - self.start) * t


@dataclass(frozen=True)
class Snap:
    segment: Segment
    t: float
    distance: float


Step = tuple[Segment, float, float]


def _projection(point: Point, a: Point, b: Point) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    squared = dx * dx + dy * dy
    t = (
        max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / squared))
        if squared
        else 0.0
    )
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy), t


class RoadGraph:
    def __init__(self, ways: Sequence[dict[str, Any]], origin: Point):
        self.grid: dict[tuple[int, int], list[Segment]] = defaultdict(list)
        self.outgoing: dict[int, list[Step]] = defaultdict(list)
        self.versions: dict[int, int] = {}
        self.locations: dict[int, Point] = {}
        self.roundabouts: set[int] = set()
        for way in ways:
            try:
                allowed = _directions(way)
            except ValueError:
                continue
            forward, backward = "forward" in allowed, "backward" in allowed
            nodes, geometry = way.get("nodes", []), way.get("geometry", [])
            if (
                len(nodes) < 2
                or len(nodes) != len(geometry)
                or any(not p for p in geometry)
            ):
                continue
            if nodes[0] == nodes[-1] and way.get("tags", {}).get("junction") in {
                "roundabout",
                "circular",
            }:
                self.roundabouts.add(way["id"])
            self.versions[way["id"]] = way.get("version", 0)
            self.locations.update(
                (node, (pos["lat"], pos["lon"])) for node, pos in zip(nodes, geometry)
            )
            xy = [_xy_m((p["lat"], p["lon"]), origin) for p in geometry]
            distances = list(
                accumulate((math.dist(a, b) for a, b in zip(xy, xy[1:])), initial=0.0)
            )
            for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
                length = distances[i + 1] - distances[i]
                if length <= 0:
                    continue
                edge = Segment(
                    way["id"],
                    a,
                    b,
                    xy[i],
                    xy[i + 1],
                    length,
                    distances[i] / distances[-1],
                    distances[i + 1] / distances[-1],
                    forward,
                    backward,
                )
                if forward:
                    self.outgoing[a].append((edge, 0.0, 1.0))
                if backward:
                    self.outgoing[b].append((edge, 1.0, 0.0))
                samples = max(1, math.ceil(length / GRID_M))
                # Adjacent cells are searched when snapping. Sampling avoids a
                # quadratic bounding-box index for long diagonal segments.
                cells = {self.cell(edge.xy(j / samples)) for j in range(samples + 1)}
                for cell in cells:
                    self.grid[cell].append(edge)

    def coordinates(self, segment: Segment, fraction: float) -> list[float]:
        lat_a, lon_a = self.locations[segment.a]
        lat_b, lon_b = self.locations[segment.b]
        return [
            round(lon_a + fraction * (lon_b - lon_a), 8),
            round(lat_a + fraction * (lat_b - lat_a), 8),
        ]

    @staticmethod
    def cell(point: Point) -> tuple[int, int]:
        return math.floor(point[0] / GRID_M), math.floor(point[1] / GRID_M)

    def snap(self, xy: Point, heading: Point) -> tuple[Optional[Snap], bool]:
        cx, cy = self.cell(xy)
        nearby = {
            s
            for i in range(cx - 2, cx + 3)
            for j in range(cy - 2, cy + 3)
            for s in self.grid.get((i, j), ())
        }
        scores: list[tuple[float, Snap]] = []
        for edge in nearby:
            distance, t = _projection(xy, edge.xy_a, edge.xy_b)
            if distance > SNAP_RADIUS_M:
                continue
            dx, dy = edge.xy_b[0] - edge.xy_a[0], edge.xy_b[1] - edge.xy_a[1]
            cosine = (dx * heading[0] + dy * heading[1]) / edge.length
            agreement = max(
                cosine if edge.forward else -1, -cosine if edge.backward else -1
            )
            scores.append((distance + 12 * (1 - agreement), Snap(edge, t, distance)))
        if not scores:
            return None, False
        scores.sort(
            key=lambda pair: (pair[0], pair[1].segment.way_id, pair[1].segment.start)
        )
        score, best = scores[0]
        ends = {best.segment.a, best.segment.b}
        ambiguous = any(
            other_score - score < 3
            and not ends.intersection((s.segment.a, s.segment.b))
            for other_score, s in scores[1:]
        )
        return best, ambiguous

    def connect(
        self, start: Snap, end: Snap, observed_length: float
    ) -> Optional[list[Step]]:
        """Dijkstra between fractional edge positions. Never joins by coordinates alone."""
        s, e = start.segment, end.segment
        if s == e and (
            (end.t >= start.t and s.forward) or (end.t <= start.t and s.backward)
        ):
            return [(s, start.t, end.t)]
        origin, target = s.xy(start.t), e.xy(end.t)
        # Off-trace detours compete poorly with roads following the observation;
        # large detours indicate an unresolved gap in the surveyed path.
        budget = 2.5 * observed_length + 70.0
        best: dict[int, float] = {}
        previous: dict[int, tuple[Optional[int], Step]] = {}
        queue: list[tuple[float, int]] = []
        for node, t, allowed in ((s.a, 0.0, s.backward), (s.b, 1.0, s.forward)):
            if not allowed and start.t != t:
                continue
            initial = abs(t - start.t) * s.length
            if initial < best.get(node, math.inf):
                best[node] = initial
                previous[node] = None, (s, start.t, t)
                heapq.heappush(queue, (initial, node))
        goals = [(e.a, 0.0, e.forward), (e.b, 1.0, e.backward)]
        winner: Optional[tuple[int, Step]] = None
        while queue:
            cost, node = heapq.heappop(queue)
            if cost > budget:
                break
            if cost > best[node]:
                continue
            for end_node, t, allowed in goals:
                if node == end_node and (allowed or t == end.t):
                    total = cost + abs(end.t - t) * e.length
                    if total <= budget:
                        budget = total
                        winner = node, (e, t, end.t)
            for edge, t0, t1 in self.outgoing.get(node, ()):
                next_node = edge.b if t1 == 1 else edge.a
                deviation, _ = _projection(edge.xy(0.5), origin, target)
                next_cost = cost + edge.length * (
                    1 + deviation / max(35.0, observed_length / 5)
                )
                if next_cost <= budget and next_cost < best.get(next_node, math.inf):
                    best[next_node] = next_cost
                    previous[next_node] = node, (edge, t0, t1)
                    heapq.heappush(queue, (next_cost, next_node))
        if winner is None:
            return None
        node, tail = winner
        path = [tail]
        while True:
            prior, step = previous[node]
            path.append(step)
            if prior is None:
                break
            node = prior
        return list(reversed(path))


def _match_ways(
    points: Sequence[Point],
    ways: Sequence[dict[str, Any]],
    input_kind: InputKind = "trace",
) -> dict[str, Any]:
    graph = RoadGraph(ways, points[0])
    xy = [_xy_m(point, points[0]) for point in points]
    snaps = []
    ambiguous = []
    # Stationary samples retain their original indices and use the next
    # nonzero heading (or the last direction of travel at the terminus).
    headings = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(xy, xy[1:])]
    heading = next((h for h in reversed(headings) if h != (0, 0)), (1.0, 0.0))
    headings.append(heading)
    for i in reversed(range(len(headings))):
        if headings[i] != (0, 0):
            heading = headings[i]
        headings[i] = heading
    for i, (point, heading) in enumerate(zip(xy, headings)):
        dx, dy = heading
        length = math.hypot(dx, dy)
        snap, multiple = graph.snap(point, (dx / length, dy / length))
        snaps.append(snap)
        if multiple:
            ambiguous.append(i)
    traversals: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    inferred_legs: list[dict[str, int]] = []
    part = 0
    geometry: dict[int, list[list[float]]] = {}
    geometry_points = 0
    for i, (start, end) in enumerate(zip(snaps, snaps[1:])):
        length = math.dist(xy[i], xy[i + 1])
        if _haversine_m(points[i], points[i + 1]) > MAX_GAP_M[input_kind]:
            reason = (
                "waypoints_over_2000m_apart"
                if input_kind == "waypoints"
                else "survey_points_over_500m_apart"
            )
        elif start is None or end is None:
            reason = "no_bus_road_within_snap_radius"
        else:
            steps = graph.connect(start, end, length)
            if steps is not None:
                for edge, t0, t1 in steps:
                    if abs(t0 - t1) * edge.length < 0.01:
                        continue
                    if geometry_points <= MAX_PREVIEW_POINTS:
                        line = geometry.setdefault(part, [])
                        for t in (t0, t1):
                            coordinate = graph.coordinates(edge, t)
                            if not line or line[-1] != coordinate:
                                line.append(coordinate)
                                geometry_points += 1
                    direction = "forward" if t1 > t0 else "backward"
                    f0, f1 = edge.fraction(t0), edge.fraction(t1)
                    last = traversals[-1] if traversals else None
                    if (
                        last
                        and last["part"] == part
                        and last["way_id"] == edge.way_id
                        and last["direction"] == direction
                        and (
                            abs(last["end_fraction"] - f0) < 1e-8
                            or (
                                edge.way_id in graph.roundabouts
                                and {last["end_fraction"], f0} == {0.0, 1.0}
                            )
                        )
                    ):
                        last["way_fraction_travelled"] += abs(f1 - f0)
                        last["end_fraction"] = f1
                        last["end_node_id"] = edge.node_at(t1)
                    else:
                        traversals.append(
                            dict(
                                way_id=edge.way_id,
                                version=graph.versions[edge.way_id],
                                direction=direction,
                                part=part,
                                way_fraction_travelled=abs(f1 - f0),
                                start_fraction=f0,
                                end_fraction=f1,
                                start_node_id=edge.node_at(t0),
                                end_node_id=edge.node_at(t1),
                            )
                        )
                if input_kind == "waypoints":
                    inferred_legs.append(
                        dict(start_point_index=i, end_point_index=i + 1)
                    )
                continue
            reason = "no_connected_bus_path_near_survey"
        gaps.append(dict(start_point_index=i, end_point_index=i + 1, reason=reason))
        part += 1
    for index, passage in enumerate(traversals):
        f0, f1 = sorted((passage["start_fraction"], passage["end_fraction"]))
        roundabout_arc = (
            passage["way_id"] in graph.roundabouts
            and 0 < index < len(traversals) - 1
            and traversals[index - 1]["part"]
            == passage["part"]
            == traversals[index + 1]["part"]
            and passage["start_node_id"] is not None
            and passage["end_node_id"] is not None
            and passage["start_node_id"] != passage["end_node_id"]
            and passage["way_fraction_travelled"] < 1
        )
        passage["roundabout_arc"] = roundabout_arc
        passage["way_fraction_travelled"] = round(passage["way_fraction_travelled"], 8)
        passage["requires_split_review"] = not roundabout_arc and (
            f0 > 1e-8 or f1 < 1 - 1e-8
        )
        # A projected mid-edge point has no existing OSM node to split at.
        passage["interior_split_node_ids"] = [
            passage[f"{end}_node_id"]
            for end in ("start", "end")
            if passage["requires_split_review"]
            and 1e-8 < passage[f"{end}_fraction"] < 1 - 1e-8
            and passage[f"{end}_node_id"] is not None
        ]
        passage["start_fraction"] = round(passage["start_fraction"], 8)
        passage["end_fraction"] = round(passage["end_fraction"], 8)
    geojson = None
    omission = None
    if geometry_points > MAX_PREVIEW_POINTS:
        omission = (
            f"Matched geometry exceeds the {MAX_PREVIEW_POINTS}-point preview limit"
        )
    else:
        features = [
            {
                "type": "Feature",
                "properties": {
                    "part": number,
                    "input_kind": input_kind,
                    "status": (
                        "inferred path"
                        if input_kind == "waypoints"
                        else "map-matched path"
                    ),
                    "bus_service_verified": False,
                    "attribution": ATTRIBUTION,
                },
                "geometry": {"type": "LineString", "coordinates": line},
            }
            for number, line in geometry.items()
            if len(line) >= 2
        ]
        collection = {"type": "FeatureCollection", "features": features}
        if (
            len(json.dumps(collection, separators=(",", ":")).encode())
            <= MAX_PREVIEW_BYTES
        ):
            geojson = collection
        else:
            omission = (
                f"Matched geometry exceeds the {MAX_PREVIEW_BYTES}-byte preview limit"
            )
    return {
        "matched_geojson": geojson,
        "geometry_omitted_reason": omission,
        "input_kind": input_kind,
        "inferred_legs": inferred_legs,
        "ordered_way_ids": [item["way_id"] for item in traversals],
        "traversals": traversals,
        "gaps": gaps,
        "ambiguous_point_indices": ambiguous,
        "continuous": bool(traversals) and not gaps,
        "requires_review": True,
        "diagnostics": {
            "snap_radius_m": SNAP_RADIUS_M,
            "input_point_count": len(points),
            "max_leg_distance_m": MAX_GAP_M[input_kind],
            "split_review_way_ids": list(
                dict.fromkeys(
                    t["way_id"] for t in traversals if t["requires_split_review"]
                )
            ),
            "turn_restrictions_and_conditional_access_checked": False,
        },
    }


def _query_chunks(
    points: Sequence[Point], input_kind: InputKind = "trace"
) -> list[list[Point]]:
    """Cover the trace with small overlapping rectangles; keep the trace itself local."""
    chunks: list[list[Point]] = []
    part = [points[0]]
    for point in points[1:]:
        if _haversine_m(part[-1], point) > MAX_GAP_M[input_kind]:
            if len(part) > 1:
                chunks.append(part)
            part = [point]
            continue
        if _haversine_m(part[0], point) > 1300 and len(part) > 1:
            chunks.append(part)
            part = [part[-1]]
        part.append(point)
    if len(part) > 1:
        chunks.append(part)
    return chunks


async def _load_highways(
    points: Sequence[Point],
    input_kind: InputKind,
    provider: Provider,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks = _query_chunks(points, input_kind)
    same_production_map = (
        config.api_environment == "production"
        and overpass.endpoint == DEFAULT_OVERPASS_URL
    )
    if provider == "overpass" and not same_production_map:
        raise ValueError(
            "The public Overpass option requires the matching production OSM target. Use editing_api for the configured target."
        )
    # Sparse stops can be offset from a road turn. Include room to explore
    # intermediate intersections without querying an entire city's graph.
    padding = 300.0 if input_kind == "waypoints" else 90.0
    if len(chunks) > 80:
        raise ValueError("Select a shorter survey range (at most 80 map windows)")
    if not chunks:
        return [], {
            "provider": "no covered survey legs",
            "environment": config.api_environment,
            "api_target": config.current_api_base_url,
            "attribution": ATTRIBUTION,
        }
    if same_production_map and provider != "editing_api":
        statements = []
        for part in chunks:
            bbox = ",".join(f"{v:.6f}" for v in _expanded_bbox(part, padding))
            statements.append(f'way["highway"]({bbox});')
        query = f'[out:json][timeout:25];({"".join(statements)});out meta geom {MAX_WAYS+1};'
        response = await overpass.execute(query)
        ways = response["elements"]
        source = {
            "provider": "Overpass",
            "data_timestamp": response.get("osm3s", {}).get("timestamp_osm_base"),
        }
    else:
        unique: dict[int, dict[str, Any]] = {}
        for part in chunks:
            nearby, _ = await _nearby_highways(part, padding)
            unique.update((way["id"], way) for way in nearby)
            if len(unique) > MAX_WAYS:
                raise ValueError("Too many roads; select a shorter survey range")
        ways = list(unique.values())
        source = {"provider": "OSM editing API"}
    if (
        len(ways) > MAX_WAYS
        or sum(len(way.get("nodes", ())) for way in ways) > MAX_GEOMETRY_POINTS
    ):
        raise ValueError("Too much road geometry; select a shorter survey range")
    return ways, {
        **source,
        "environment": config.api_environment,
        "api_target": config.current_api_base_url,
        "attribution": ATTRIBUTION,
    }


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
async def suggest_bus_route_ways(
    points: Optional[
        Annotated[list[SurveyPoint], Field(min_length=2, max_length=5000)]
    ] = None,
    selection_id: Optional[str] = None,
    input_kind: InputKind = "trace",
    provider: Provider = "auto",
) -> dict[str, Any]:
    """Match ordered survey coordinates or one GPX selection to existing, directional OSM ways.
    Use input_kind=waypoints for ordered field-observed stops or street turn coordinates.
    Connected legs up to 2 km are inferred road paths requiring independent confirmation.
    Dense trace legs accept sampling gaps up to 500 m. provider=editing_api uses the
    configured map API directly when public Overpass is unavailable. Only bounding boxes
    leave the server. matched_geojson contains one clipped road line per connected part.
    geometry_omitted_reason explains when the preview exceeds the output limit.
    Fractions use the OSM way's node
    order (0 to 1). Inspect gaps, ambiguity, split candidates and turn restrictions before
    using the ordered way IDs in a route preview. This tool performs no OSM edits.
    """
    try:
        if (points is None) == (selection_id is None):
            raise ValueError("Provide exactly one of points or selection_id")
        survey = (
            _resolve_track_selection(selection_id).points
            if selection_id is not None
            else tuple((p.lat, p.lon) for p in (points or []))
        )
        if not 2 <= len(survey) <= 5000:
            raise ValueError("Provide 2–5000 ordered survey points")
        if any(not (-90 < lat < 90 and -180 <= lon <= 180) for lat, lon in survey):
            raise ValueError("Survey coordinates must be finite and inside map bounds")
        if any(abs(a[1] - b[1]) > 180 for a, b in zip(survey, survey[1:])):
            raise ValueError("Split the selection where it crosses the antimeridian")
        if all(point == survey[0] for point in survey):
            raise ValueError("Survey points must describe movement")
        if input_kind not in MAX_GAP_M or provider not in {
            "auto",
            "overpass",
            "editing_api",
        }:
            raise ValueError("Unsupported input_kind or provider")
        ways, source = await _load_highways(survey, input_kind, provider)
        match = _match_ways(survey, ways, input_kind)
        if match["matched_geojson"] is not None:
            match["matched_geojson"]["source"] = source
        return {
            "success": True,
            "data": {**match, "source": source, "selection_id": selection_id},
        }
    except Exception as exc:
        return failure(exc, "Could not match the surveyed bus path")
