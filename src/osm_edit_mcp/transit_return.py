"""Review an independently matched return trip against the outward bus stops."""

from collections import Counter
from itertools import groupby
from typing import Annotated, Any, Literal, NamedTuple, Optional

from pydantic import BaseModel, Field, StrictInt

from .app import profile_tool
from .config import config
from .discovery_errors import failure
from .http_client import get_public_client
from .track_tools import Point, _haversine_m
from .transit_corridor import Parts, Side, _analyze_stops, _matched_parts, _stop_nodes
from .transit_data import _bulk_read
from .transit_geometry import _role
from .transit_match import Provider
from .transit_tools import READ, ObjectId


class MatchedPassage(BaseModel):
    way_id: ObjectId
    part: Annotated[StrictInt, Field(ge=0)]
    direction: Literal["forward", "backward"]
    start_node_id: Optional[ObjectId]
    end_node_id: Optional[ObjectId]


class BusTripMatch(BaseModel):
    """Fields consumed from suggest_bus_route_ways data, in travel order."""

    input_kind: Literal["trace", "waypoints"]
    matched_geojson: dict[str, Any]
    traversals: Annotated[list[MatchedPassage], Field(max_length=8000)]
    gaps: Annotated[list[dict[str, Any]], Field(max_length=5000)]
    ambiguous_point_indices: Annotated[list[StrictInt], Field(max_length=5000)]


def _trip_parts(trip: BusTripMatch) -> Parts:
    parts, _ = _matched_parts(trip.matched_geojson)
    if not parts:
        raise ValueError(
            "The trip has no matched roads. Review the road match and its gaps."
        )
    traversal_parts = [
        part for part, _ in groupby(trip.traversals, key=lambda p: p.part)
    ]
    if traversal_parts != list(parts):
        raise ValueError("Road traversal parts must match the geometry in travel order")
    return parts


class Turn(NamedTuple):
    from_way: int
    from_direction: str
    junction: int
    to_way: int
    to_direction: str

    def reverse(self) -> "Turn":
        reverse_direction = {"forward": "backward", "backward": "forward"}
        return Turn(
            self.to_way,
            reverse_direction[self.to_direction],
            self.junction,
            self.from_way,
            reverse_direction[self.from_direction],
        )


def _turns(passages: list[MatchedPassage]) -> list[tuple[int, Turn]]:
    turns = []
    for before, after in zip(passages, passages[1:]):
        junction = before.end_node_id
        if before.part == after.part and junction and junction == after.start_node_id:
            turns.append(
                (
                    before.part,
                    Turn(
                        before.way_id,
                        before.direction,
                        junction,
                        after.way_id,
                        after.direction,
                    ),
                )
            )
    return turns


def _road_differences(trip: BusTripMatch, other: BusTripMatch) -> dict[str, Any]:
    base = config.current_web_base_url
    other_way_ids = {entry.way_id for entry in other.traversals}
    reversed_turns = Counter(turn.reverse() for _, turn in _turns(other.traversals))
    differences = []
    for part, turn in _turns(trip.traversals):
        if reversed_turns[turn]:
            reversed_turns[turn] -= 1
        else:
            differences.append(
                {
                    "part": part,
                    "from_way_id": turn.from_way,
                    "from_direction": turn.from_direction,
                    "via_node_id": turn.junction,
                    "to_way_id": turn.to_way,
                    "to_direction": turn.to_direction,
                    "junction_url": f"{base}/node/{turn.junction}",
                }
            )
    return {
        "ways_only_in_this_direction": [
            {**p.model_dump(), "osm_url": f"{base}/way/{p.way_id}"}
            for p in trip.traversals
            if p.way_id not in other_way_ids
        ],
        "turns_without_reverse_counterpart": differences,
    }


def _endpoint_pair(outward: Point, returning: Point) -> dict[str, Any]:
    return {
        "outward": {"lat": outward[0], "lon": outward[1]},
        "return": {"lat": returning[0], "lon": returning[1]},
        "distance_m": round(_haversine_m(outward, returning), 1),
    }


def _pair_stops(
    outward_ids: list[int],
    nodes: dict[int, dict[str, Any]],
    corridor: dict[str, Any],
    pair_radius_m: float,
) -> dict[str, Any]:
    visits = sorted(
        (
            v
            for group in ("candidates", "ambiguous", "opposite", "excluded")
            for v in corridor[group]
        ),
        key=lambda v: (v["part"], v["along_m"], v["distance_m"], v["node_id"]),
    )
    outward = []
    candidate_uses: Counter[int] = Counter()
    linked: set[int] = set()
    link_count = 0
    for order, node_id in enumerate(outward_ids, 1):
        node = nodes[node_id]
        name = node["tags"].get("name", "")
        nearby = []
        for index, visit in enumerate(visits):
            distance = _haversine_m(
                (node["lat"], node["lon"]), (visit["lat"], visit["lon"])
            )
            if distance > pair_radius_m:
                continue
            link_count += 1
            if link_count > 6000:
                raise ValueError(
                    "Too many nearby stop pairs. Reduce the pairing radius or compare a shorter section."
                )
            status = "excluded" if visit["excluded"] else visit["status"]
            nearby.append(
                {
                    "return_visit_index": index,
                    "status": status,
                    "distance_m": round(distance, 1),
                    "same_node": node_id == visit["node_id"],
                    "same_name": bool(name.strip())
                    and name.strip().casefold() == visit["name"].strip().casefold(),
                }
            )
            linked.add(index)
            if status == "candidate":
                candidate_uses[index] += 1
        outward.append(
            {
                "outward_sequence": order,
                "node_id": node_id,
                "role": _role(node),
                "name": name,
                "lat": node["lat"],
                "lon": node["lon"],
                "osm_url": f"{config.current_web_base_url}/node/{node_id}",
                "nearby_return_visits": sorted(
                    nearby, key=lambda row: row["distance_m"]
                ),
            }
        )
    for stop in outward:
        links = stop["nearby_return_visits"]
        candidates = [
            row["return_visit_index"] for row in links if row["status"] == "candidate"
        ]
        statuses = {row["status"] for row in links}
        if (
            "ambiguous" in statuses
            or len(candidates) > 1
            or any(candidate_uses[i] > 1 for i in candidates)
        ):
            status = "ambiguous"
        elif candidates:
            status = "candidate"
        elif "opposite" in statuses:
            status = "opposite_side_only"
        elif links:
            status = "excluded_only"
        else:
            status = "missing"
        stop["pair_status"] = status
    return {
        "outward_stops": outward,
        "return_visits": [
            {
                **v,
                "return_visit_index": i,
                "status": "excluded" if v["excluded"] else v["status"],
                "boarding_status": v["status"],
            }
            for i, v in enumerate(visits)
        ],
        "unpaired_return_candidate_indices": [
            i
            for i, v in enumerate(visits)
            if i not in linked and v["status"] == "candidate" and not v["excluded"]
        ],
    }


@profile_tool(annotations=READ)
async def review_bus_return_trip(
    outward_stop_ids: Annotated[list[ObjectId], Field(min_length=1, max_length=250)],
    return_match: BusTripMatch,
    outward_match: Optional[BusTripMatch] = None,
    driving_side: Side = "right",
    corridor_radius_m: Annotated[float, Field(ge=1, le=100)] = 35.0,
    pair_radius_m: Annotated[float, Field(ge=1, le=500)] = 120.0,
    excluded_return_node_ids: Optional[
        Annotated[list[ObjectId], Field(max_length=250)]
    ] = None,
    provider: Provider = "auto",
) -> dict[str, Any]:
    """Compare confirmed outward stops with a separately observed return journey.
    Supply return_match as the data from suggest_bus_route_ways for an actual return
    GPX selection or surveyed waypoints in return travel order. Optional outward_match
    from the outward trip adds differences in OSM ways, junctions and matched endpoints.
    Return visits follow the return trace, with boarding side, ambiguity and exclusions.
    Pairs use geographic distance even when local names differ. Review every candidate.
    The editing API receives the outward node IDs. Only return corridor bounding boxes
    are sent to the stop provider. This read-only comparison never establishes service.
    """
    try:
        return_parts = _trip_parts(return_match)
        outward_parts = _trip_parts(outward_match) if outward_match is not None else {}
        async with get_public_client() as client:
            nodes = await _bulk_read(client, "node", set(outward_stop_ids))
        for identifier, node in nodes.items():
            if not _role(node):
                raise ValueError(
                    f"Outward node/{identifier} is not a mapped bus platform or stop position"
                )
        map_nodes, source = await _stop_nodes(return_parts, corridor_radius_m, provider)
        corridor = _analyze_stops(
            return_parts,
            return_match.gaps,
            map_nodes,
            driving_side,
            corridor_radius_m,
            set(excluded_return_node_ids or []),
        )
        pairs = _pair_stops(outward_stop_ids, nodes, corridor, pair_radius_m)
        data = {
            **pairs,
            "source": source,
            "service_verified": False,
            "pair_radius_m": pair_radius_m,
            **{
                k: corridor[k]
                for k in (
                    "driving_side",
                    "radius_m",
                    "covered_distance_m",
                    "part_count",
                    "excluded_node_ids",
                )
            },
            "return_input_kind": return_match.input_kind,
            "return_gaps": return_match.gaps,
            "return_ambiguous_point_indices": return_match.ambiguous_point_indices,
        }
        if outward_match is not None:
            data["road_comparison"] = {
                "outward": _road_differences(outward_match, return_match),
                "return": _road_differences(return_match, outward_match),
                "matched_endpoints": {
                    "outward_start_return_end": _endpoint_pair(
                        next(iter(outward_parts.values()))[0],
                        next(reversed(return_parts.values()))[-1],
                    ),
                    "outward_end_return_start": _endpoint_pair(
                        next(reversed(outward_parts.values()))[-1],
                        next(iter(return_parts.values()))[0],
                    ),
                },
                "outward_input_kind": outward_match.input_kind,
                "outward_gaps": outward_match.gaps,
                "outward_ambiguous_point_indices": outward_match.ambiguous_point_indices,
            }
        return {"success": True, "data": data}
    except Exception as exc:
        return failure(exc, "Could not compare the bus return trip")
