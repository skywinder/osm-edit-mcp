"""Geometry checks for one surveyed direction of an existing-road bus route."""

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .nearby import bounded_integer, validate_point
from .poi_duplicates import geometry_distance

EARTH_RADIUS_M = 6_371_008.8

Record = dict[str, Any]
Point = tuple[float, float]  # latitude, longitude
# Platforms are usually offset from the road centre. A projection far inside the
# first/last way requires a split or a mapper's review of a terminal loop.
TERMINUS_TOLERANCE_M = 12.0
BUS_ROADS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "busway",
    "bus_guideway",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}
ACCESS_KEYS = ("bus", "psv", "motor_vehicle", "vehicle", "access")
ALLOWED = {"yes", "designated", "permissive", "official"}


class _AmbiguousVisit(ValueError):
    """A feasible traversal with multiple stop assignments blocks publication."""


def _point(node: Record) -> Point:
    lat, lon = node.get("lat"), node.get("lon")
    validate_point(lat, lon)
    return float(node["lat"]), float(node["lon"])


def _distance(a: Point, b: Point) -> float:
    return geometry_distance({"type": "Point", "coordinates": [b[1], b[0]]}, a)


def _role(node: Record) -> str | None:
    tags = node.get("tags", {})
    if node.get("type", "node") != "node" or tags.get("bus") == "no":
        return None
    highway, pt = tags.get("highway"), tags.get("public_transport")
    if (
        tags.get("bus") != "yes"
        and highway != "bus_stop"
        and (
            "railway" in tags
            or any(
                tags.get(k) == "yes"
                for k in ("train", "tram", "subway", "ferry", "light_rail")
            )
        )
    ):
        return None
    if pt == "stop_position":
        return "stop"
    if pt == "platform" or highway in {"bus_stop", "platform"}:
        return "platform"
    return None


def match_stop_candidates(
    lat: float,
    lon: float,
    candidates: Sequence[Record],
    *,
    radius_m: float = 50,
    limit: int = 5,
) -> list[Record]:
    """Rank existing nodes around a surveyed point without relying on their names."""
    validate_point(lat, lon)
    bounded_integer(limit, "limit", 20)
    if not 0 < radius_m <= 500 or len(candidates) > 10000:
        raise ValueError(
            "Search radius must be at most 500 m and input at most 10000 nodes"
        )
    matches = []
    seen = set()
    for node in candidates:
        role = _role(node)
        if not role or node["id"] in seen:
            continue
        seen.add(node["id"])
        point = _point(node)
        distance = _distance((lat, lon), point)
        if distance <= radius_m:
            matches.append(
                {
                    "id": node["id"],
                    "name": node.get("tags", {}).get("name"),
                    "lat": point[0],
                    "lon": point[1],
                    "role": role,
                    "distance_m": round(distance, 2),
                }
            )
    return sorted(matches, key=lambda item: (item["distance_m"], item["id"]))[:limit]


def _access(tags: Record, direction: str) -> str | None:
    for mode in ACCESS_KEYS:
        for key in (f"{mode}:{direction}", mode):
            if f"{key}:conditional" in tags:
                return "conditional"
            if key in tags:
                return str(tags[key])
    return None


def _check_road_nodes(chain: list["Traversal"], nodes: dict[int, Record]) -> None:
    for step in chain:
        for ref in step.refs:
            tags = nodes[ref].get("tags", {})
            if not tags:
                continue
            access = _access(tags, step.direction)
            if access is not None and access not in ALLOWED:
                raise ValueError(
                    f"Road node {ref} has restricted or conditional bus access"
                )
            if tags.get("locked") != "yes" and tags.get("barrier") not in {
                "bollard",
                "block",
                "cycle_barrier",
                "stile",
                "turnstile",
                "jersey_barrier",
                "kissing_gate",
                "log",
                "wall",
                "fence",
                "chain",
            }:
                continue
            # Treat an explicit bus/PSV exception independently of general
            # access. A publicly accessible bollard may be intended for walkers.
            if not any(
                tags.get(key) in ALLOWED
                for mode in ("bus", "psv")
                for key in (f"{mode}:{step.direction}", mode)
            ):
                raise ValueError(
                    f"Barrier at road node {ref} requires an explicit bus access exception"
                )


def _directions(way: Record) -> list[str]:
    tags = way.get("tags", {})
    highway = tags.get("highway")
    if (
        not highway
        or highway in {"construction", "proposed", "steps"}
        or tags.get("area") == "yes"
    ):
        raise ValueError(f"Way {way['id']} is not a usable bus road")
    oneway = (
        "yes" if highway == "motorway" or tags.get("junction") == "roundabout" else "no"
    )
    for key in (
        "oneway:bus",
        "oneway:psv",
        "oneway:motor_vehicle",
        "oneway:vehicle",
        "oneway",
    ):
        if f"{key}:conditional" in tags:
            raise ValueError(
                f"Way {way['id']} has conditional one-way bus access requiring review"
            )
        if key in tags:
            oneway = tags[key]
            break
    options = {
        "yes": ["forward"],
        "true": ["forward"],
        "1": ["forward"],
        "-1": ["backward"],
        "no": ["forward", "backward"],
        "false": ["forward", "backward"],
        "0": ["forward", "backward"],
    }.get(oneway, [])
    permitted = []
    for direction in options:
        permission = _access(tags, direction)
        vehicle_permission = any(
            key in tags
            for mode in ACCESS_KEYS[:-1]
            for key in (mode, f"{mode}:{direction}")
        )
        if (highway in BUS_ROADS or vehicle_permission) and (
            permission in ALLOWED or permission is None
        ):
            permitted.append(direction)
    if not permitted:
        raise ValueError(
            f"Way {way['id']} has ambiguous or prohibited bus access or one-way direction"
        )
    return permitted


@dataclass(frozen=True)
class Traversal:
    way_id: int
    direction: str
    refs: tuple[int, ...]


def _choices(
    way: Record, before: Record | None, after: Record | None
) -> list[Traversal]:
    way_id = way["id"]
    directions = _directions(way)
    refs = tuple(way.get("nodes", ()))
    if len(refs) < 2 or len(set(refs)) < 2:
        raise ValueError(f"Way {way_id} has incomplete geometry")
    if refs[0] != refs[-1]:
        return [
            Traversal(way_id, d, refs if d == "forward" else refs[::-1])
            for d in directions
        ]
    if (
        way.get("tags", {}).get("junction") not in {"roundabout", "circular"}
        or not before
        or not after
    ):
        raise ValueError(f"Closed way {way_id} needs review of the entry and exit")
    ring = refs[:-1]
    if len(set(ring)) != len(ring):
        raise ValueError(f"Roundabout {way_id} has ambiguous geometry")
    entries = {before["nodes"][0], before["nodes"][-1]} & set(ring)
    exits = {after["nodes"][0], after["nodes"][-1]} & set(ring)
    choices = []
    for direction in directions:
        ordered = ring if direction == "forward" else ring[::-1]
        for entry in entries:
            rotated = ordered[ordered.index(entry) :] + ordered[: ordered.index(entry)]
            for exit_node in exits - {entry}:
                choices.append(
                    Traversal(
                        way_id, direction, rotated[: rotated.index(exit_node) + 1]
                    )
                )
    if not choices:
        raise ValueError(
            f"Roundabout {way_id} needs distinct entry and exit at connected way endpoints"
        )
    return choices


def _chains(ordered: list[Record]) -> list[list[Traversal]]:
    chains: list[list[Traversal]] = [[]]
    for i, way in enumerate(ordered):
        choices = _choices(
            way,
            ordered[i - 1] if i else None,
            ordered[i + 1] if i + 1 < len(ordered) else None,
        )
        chains = [
            chain + [step]
            for chain in chains
            for step in choices
            if not chain or chain[-1].refs[-1] == step.refs[0]
        ]
        if not chains:
            raise ValueError(
                f"Way {way['id']} is disconnected or in the wrong direction for bus access. Check shared endpoints, one-way tags and necessary way splits"
            )
        if len(chains) > 8:
            raise ValueError("Ambiguous road direction: too many connected traversals")
    return chains


@dataclass(frozen=True)
class Edge:
    start: Point
    east: float
    north: float
    scale_lon: float
    length: float
    along: float

    def projection(self, point: Point) -> tuple[float, float, float, float]:
        x = ((point[1] - self.start[1] + 180) % 360 - 180) * self.scale_lon
        y = math.radians(point[0] - self.start[0]) * EARTH_RADIUS_M
        longitudinal = (x * self.east + y * self.north) / self.length
        fraction = max(0.0, min(1.0, longitudinal / self.length))
        distance = math.hypot(x - fraction * self.east, y - fraction * self.north)
        cross = (self.east * y - self.north * x) / self.length
        return distance, self.along + fraction * self.length, cross, longitudinal


def _edges(
    refs: list[int], nodes: dict[int, Record], directions: list[str]
) -> tuple[list[Edge], dict[int, list[tuple[float, str | None]]], float]:
    edges = []
    along = 0.0
    positions: dict[int, list[tuple[float, str | None]]] = {
        refs[0]: [(0, directions[0])]
    }
    previous = _point(nodes[refs[0]])
    for index, ref in enumerate(refs[1:], start=1):
        current = _point(nodes[ref])
        scale = (
            math.radians(1)
            * EARTH_RADIUS_M
            * math.cos(math.radians((previous[0] + current[0]) / 2))
        )
        east = ((current[1] - previous[1] + 180) % 360 - 180) * scale
        north = math.radians(current[0] - previous[0]) * EARTH_RADIUS_M
        length = math.hypot(east, north)
        if length:
            edges.append(Edge(previous, east, north, scale, length, along))
            along += length
        # A direction relative to the OSM way is indeterminate at a join when
        # the arriving and departing ways are digitized in opposite directions.
        direction = directions[index - 1]
        consistent = index == len(directions) or directions[index] == direction
        positions.setdefault(ref, []).append((along, direction if consistent else None))
        previous = current
    if not edges:
        raise ValueError("The selected bus path has zero length")
    return edges, positions, along


def _platform_matches(
    point: Point,
    edges: list[Edge],
    radius: float,
    driving_side: str,
    *,
    at_start: bool,
    at_end: bool,
) -> list[tuple[float, float]]:
    # A platform may be passed more than once. Retain distinct local minima,
    # then resolve occurrences using the supplied stop order and termini.
    nearby: list[tuple[float, float]] = []
    projections = [edge.projection(point) for edge in edges]
    if (at_start and projections[0][3] < -TERMINUS_TOLERANCE_M) or (
        at_end and projections[-1][3] > edges[-1].length + TERMINUS_TOLERANCE_M
    ):
        raise ValueError("Terminus platform lies past the selected road endpoint")
    for i, (distance, along, cross, _) in enumerate(projections):
        if distance > radius:
            continue
        # Requiring a local minimum avoids snapping a wrong-side platform to a
        # distant segment endpoint just because that segment points another way.
        if i and projections[i - 1][0] < distance - 0.01:
            continue
        if i + 1 < len(projections) and projections[i + 1][0] < distance - 0.01:
            continue
        if (cross if driving_side == "left" else -cross) < 0.25:
            continue
        if nearby and abs(along - nearby[-1][0]) < 0.5:
            if distance < nearby[-1][1]:
                nearby[-1] = (along, distance)
        else:
            nearby.append((along, distance))
    return nearby


def _same_boarding_site(stop: Record, platform: Record) -> bool:
    # An offset allowance is only meaningful for the passenger/vehicle members
    # of one call. Conflicting references or names should remain visible.
    first, second = stop.get("tags", {}), platform.get("tags", {})
    keys = {"name", "ref", "local_ref"} | {k for k in first if k.startswith("name:")}
    shared = [k for k in keys if first.get(k) and second.get(k)]
    if any(first[k].strip().casefold() != second[k].strip().casefold() for k in shared):
        return False
    return _distance(_point(stop), _point(platform)) <= (25 if shared else 15)


def _locate(
    stops: list[Record],
    refs: list[int],
    directions: list[str],
    nodes: dict[int, Record],
    radius: float,
    side: str,
) -> tuple[list[Record], float]:
    edges, positions, length = _edges(refs, nodes, directions)
    if len(edges) * len(stops) > 2_000_000:
        raise ValueError("Route too large for bounded stop projection")
    options: list[list[tuple[float, float]]] = []
    uncertain_directions: dict[int, set[float]] = {}
    roles: list[str] = []
    for i, node in enumerate(stops):
        stop_id = node["id"]
        role = _role(node)
        if not role:
            raise ValueError(
                f"Node {stop_id} is not a mapped bus platform or stop position"
            )
        if role == "stop":
            visits = positions.get(stop_id, [])
            if not visits:
                raise ValueError(
                    f"Stop position {stop_id} is not a node of the route road"
                )
            tags = node.get("tags", {})
            direction = tags.get(
                "stop_position:direction", tags.get("direction", "both")
            )
            if direction not in {"forward", "backward", "both"}:
                raise ValueError(
                    f"Stop position {stop_id} has an unsupported travel direction"
                )
            if direction != "both":
                uncertain_directions[i] = {
                    at for at, actual in visits if actual is None
                }
            matches = [
                (at, 0.0)
                for at, actual in visits
                if direction == "both" or actual is None or direction == actual
            ]
            if not matches:
                raise ValueError(
                    f"Stop position {stop_id} has a conflicting or ambiguous travel direction"
                )
        else:
            matches = _platform_matches(
                _point(node),
                edges,
                radius,
                side,
                at_start=i == 0,
                at_end=i == len(stops) - 1,
            )
            if not matches:
                raise ValueError(
                    f"Platform {stop_id} is too far from the route, on the wrong side, or has ambiguous boarding side"
                )
            if i and roles[-1] == "stop" and _same_boarding_site(stops[i - 1], node):
                # A bus can stop with the platform beside its rear door. Keep
                # both PTv2 members at the vehicle's station in this case, so
                # subsequent, unrelated stops must still follow that station.
                aligned: list[tuple[float, float]] = []
                for at, distance in matches:
                    nearby_visits = [
                        visit for visit, _ in options[-1] if 0 <= visit - at <= 12
                    ]
                    aligned.extend((visit, distance) for visit in nearby_visits or [at])
                matches = sorted(set(aligned))
        roles.append(role)
        if i == 0 or i == len(stops) - 1:
            target = 0.0 if i == 0 else length
            tolerance = 0.01 if role == "stop" else TERMINUS_TOLERANCE_M
            matches = [hit for hit in matches if abs(hit[0] - target) <= tolerance]
            if not matches:
                raise ValueError(
                    f"Terminus {stop_id} is inside or outside the selected ways. Check where the bus starts or ends and whether a way must be split"
                )
        options.append(matches)
    # The earliest and latest legal assignments bound every feasible sequence.
    # Different answers mean more than one visit fits the supplied evidence.
    earliest = []
    previous = -math.inf
    for i, matches in enumerate(options):
        minimum = 0.0 if i and roles[i - 1 : i + 1] == ["stop", "platform"] else 0.01
        hit = next((h for h in matches if h[0] >= previous + minimum), None)
        if hit is None:
            raise ValueError(f"Stop {stops[i]['id']} is out of travel order")
        earliest.append(hit)
        previous = hit[0]
    following = math.inf
    for i in reversed(range(len(options))):
        minimum = 0.0 if roles[i : i + 2] == ["stop", "platform"] else 0.01
        hit = next(
            h for h in reversed(options[i]) if h[0] <= following - minimum + 1e-8
        )
        if hit[0] - earliest[i][0] > 0.5:
            raise _AmbiguousVisit(
                f"Stop {stops[i]['id']} matches multiple visits on this route"
            )
        if earliest[i][0] in uncertain_directions.get(i, set()):
            raise _AmbiguousVisit(
                f"Stop position {stops[i]['id']} has ambiguous travel direction at a way junction"
            )
        following = hit[0]
    return [
        {
            "id": node["id"],
            "role": role,
            "along_m": round(along, 2),
            "distance_m": round(distance, 2),
        }
        for node, role, (along, distance) in zip(stops, roles, earliest)
    ], length


def validate_route_geometry(
    way_ids: Sequence[int],
    stop_ids: Sequence[int],
    ways: dict[int, Record],
    nodes: dict[int, Record],
    *,
    driving_side: str = "right",
    max_stop_distance_m: float = 50,
) -> Record:
    """Check an ordered way and node selection, without inferring transit service."""
    if not 1 <= len(way_ids) <= 1000 or not 2 <= len(stop_ids) <= 250:
        raise ValueError("Provide 1–1000 ordered ways and 2–250 ordered stop nodes")
    if driving_side not in {"left", "right"} or not 0 < max_stop_distance_m <= 200:
        raise ValueError(
            "Choose right or left driving side and a stop radius of at most 200 m"
        )
    try:
        ordered = [ways[ref] for ref in way_ids]
        stops = [nodes[ref] for ref in stop_ids]
    except KeyError as exc:
        raise ValueError(f"Missing selected OSM object {exc.args[0]}") from exc
    if sum(len(way.get("nodes", [])) for way in ordered) > 50_000:
        raise ValueError("Route too large for bounded way traversal")
    for way in ordered:
        if len(way.get("nodes", [])) < 2:
            raise ValueError(f"Way {way['id']} lacks nodes")
        for ref in way["nodes"]:
            if ref not in nodes:
                raise ValueError(f"Missing road geometry node {ref} on way {way['id']}")
    valid = []
    errors = []
    for chain in _chains(ordered):
        refs = [chain[0].refs[0]] + [ref for step in chain for ref in step.refs[1:]]
        directions = [step.direction for step in chain for _ in step.refs[1:]]
        try:
            _check_road_nodes(chain, nodes)
            located, length = _locate(
                stops, refs, directions, nodes, max_stop_distance_m, driving_side
            )
        except _AmbiguousVisit:
            raise
        except ValueError as exc:
            errors.append(str(exc))
            continue
        valid.append(
            {
                "length_m": round(length, 2),
                "traversals": [
                    {
                        "way_id": step.way_id,
                        "direction": step.direction,
                        "from_node": step.refs[0],
                        "to_node": step.refs[-1],
                    }
                    for step in chain
                ],
                "stops": located,
                "node_ids": refs,
            }
        )
    if not valid:
        raise ValueError("; ".join(dict.fromkeys(errors)))
    if len(valid) != 1:
        raise ValueError(
            "Ambiguous traversal: more than one connected road direction fits the stops"
        )
    return valid[0]
