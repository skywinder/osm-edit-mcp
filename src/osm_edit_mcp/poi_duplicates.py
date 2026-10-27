"""Deterministic, conservative POI duplicate signals for point creation.

Distances are metres to the actual returned geometry, never its centroid.
These are review thresholds, not assertions that two OSM objects are identical.
The bounded search and conservative relation-member geometry remain explicit
limitations of the node creation workflow.
"""

import math
import unicodedata
from typing import Any, Dict, List, Tuple

POI_KEYS = frozenset(
    ("shop", "amenity", "tourism", "leisure", "office", "craft", "healthcare")
)
UNSPECIFIED = frozenset(("yes", "no", "none", "unknown", "fixme"))
POLICY: Dict[str, Any] = {
    "version": 1,
    "distance_method": "minimum distance to returned geometry; zero inside areas",
    "default": {"possible_m": 25.0, "likely_m": 5.0},
    "leisure=pitch": {
        "possible_m": 35.0,
        "likely_m": 8.0,
        "matching_sport_likely_m": 15.0,
    },
    "leisure=swimming_pool": {"possible_m": 20.0, "likely_m": 5.0},
    "leisure=beach_resort": {"possible_m": 75.0, "likely_m": 15.0},
}


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _values(value: str) -> set[str]:
    return {_normalized(part) for part in value.split(";") if part.strip()}


def _xy(point: List[float], origin: Tuple[float, float]) -> Tuple[float, float]:
    lat, lon = origin
    return (
        math.radians((point[0] - lon + 180) % 360 - 180)
        * 6_371_008.8
        * math.cos(math.radians(lat)),
        math.radians(point[1] - lat) * 6_371_008.8,
    )


def _line_distance(line: List[List[float]], point: Tuple[float, float]) -> float:
    if len(line) < 2:
        raise ValueError("Duplicate candidate has incomplete line geometry")
    distances = []
    projected = [_xy(vertex, point) for vertex in line]
    for (ax, ay), (bx, by) in zip(projected, projected[1:]):
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        t = (
            max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
            if denominator
            else 0.0
        )
        distances.append(math.hypot(ax + t * dx, ay + t * dy))
    return min(distances)


def _in_ring(ring: List[List[float]], point: Tuple[float, float]) -> bool:
    inside = False
    xy = [_xy(vertex, point) for vertex in ring]
    for (ax, ay), (bx, by) in zip(xy, xy[1:]):
        if (ay > 0) != (by > 0) and 0 < (bx - ax) * -ay / (by - ay) + ax:
            inside = not inside
    return inside


def geometry_distance(geometry: Dict[str, Any], point: Tuple[float, float]) -> float:
    kind = geometry["type"]
    if kind == "GeometryCollection":
        return min(
            geometry_distance(member, point) for member in geometry["geometries"]
        )
    coordinates = geometry["coordinates"]
    if kind == "Point":
        lat, lon = map(math.radians, point)
        other_lon, other_lat = map(math.radians, coordinates)
        value = (
            math.sin((other_lat - lat) / 2) ** 2
            + math.cos(lat) * math.cos(other_lat) * math.sin((other_lon - lon) / 2) ** 2
        )
        return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, value)))
    if kind == "LineString":
        return _line_distance(coordinates, point)
    if kind == "Polygon":
        boundary = min(_line_distance(ring, point) for ring in coordinates)
        if boundary < 0.01 or (
            _in_ring(coordinates[0], point)
            and not any(_in_ring(hole, point) for hole in coordinates[1:])
        ):
            return 0.0
        return boundary
    raise ValueError("Duplicate candidate has unsupported geometry")


def _identities(tags: Dict[str, str]) -> Tuple[set[str], set[str]]:
    names, contacts = set(), set()
    for key, value in tags.items():
        if key in {
            "name",
            "official_name",
            "alt_name",
            "old_name",
            "short_name",
        } or key.startswith("name:"):
            names.update(_values(value))
        contact_key = key.removeprefix("contact:")
        if contact_key in {"phone", "mobile", "email", "website"}:
            for item in _values(value):
                if contact_key in {"phone", "mobile"}:
                    item = "".join(
                        character for character in item if character.isdigit()
                    )
                    contact_key = "phone"
                if item:
                    contacts.add(f"{contact_key}:{item.rstrip('/')}")
    return names, contacts


def review_candidates(
    candidates: List[Dict[str, Any]], node: Dict[str, Any]
) -> List[Dict[str, Any]]:
    tags = node["tags"]
    point = (float(node["lat"]), float(node["lon"]))
    names, contacts = _identities(tags)
    thresholds = POLICY.get(f"leisure={tags.get('leisure')}", POLICY["default"])
    reviewed = []
    for candidate in candidates:
        other = candidate["tags"]
        distance = geometry_distance(candidate["geometry"], point)
        shared_keys = POI_KEYS & tags.keys() & other.keys()
        same_kind = any(
            (_values(tags[key]) - UNSPECIFIED) & (_values(other[key]) - UNSPECIFIED)
            for key in shared_keys
        )
        unknown_kind = any(
            not (_values(other[key]) - UNSPECIFIED) for key in shared_keys
        )
        other_names, other_contacts = _identities(other)
        name_match, contact_match = bool(names & other_names), bool(
            contacts & other_contacts
        )
        reasons = [f"Distance to existing geometry: {distance:.3f} m"]
        if same_kind:
            reasons.append("Matching explicit POI type")
        elif unknown_kind:
            reasons.append("Existing POI type is unspecified")
        else:
            reasons.append(
                "Different explicit POI types; a shared broad key alone is not a duplicate signal"
            )
        likely_distance = thresholds["likely_m"]
        if tags.get("leisure") == other.get("leisure") == "pitch":
            sports, other_sports = _values(tags.get("sport", "")), _values(
                other.get("sport", "")
            )
            unknown_sport = (
                not sports
                or not other_sports
                or bool((sports | other_sports) & (UNSPECIFIED | {"multi"}))
            )
            if (sports & other_sports) - UNSPECIFIED - {"multi"}:
                reasons.append(
                    "Matching sport, including semicolon-separated sport lists"
                )
                likely_distance = thresholds["matching_sport_likely_m"]
            if unknown_sport:
                reasons.append(
                    "Missing, unspecified or multi sport is unknown; it does not establish distinct courts"
                )
            elif not sports & other_sports:
                reasons.append(
                    "Different sports reduce similarity but can describe a multifunctional or retagged court"
                )
        if name_match:
            reasons.append("Matching name or name variant")
        elif names and other_names:
            reasons.append("Different names do not rule out renaming")
        if contact_match:
            reasons.append(
                "Matching contact information; shared operator contacts still need review"
            )
        area_overlap = distance == 0 and candidate["geometry"]["type"] != "Point"
        if area_overlap:
            reasons.append(
                "Proposed point intersects existing area or line geometry; containment alone is not identity"
            )
        retail_overlap = (
            "shop" in tags
            and other.get("building") in {"retail", "supermarket"}
            and area_overlap
        )
        near = distance <= thresholds["possible_m"]
        classification = "context_only"
        if (
            (same_kind or unknown_kind)
            and near
            or name_match
            or contact_match
            or retail_overlap
        ):
            classification = "possible_duplicate"
            if same_kind and (
                distance <= likely_distance or name_match or contact_match
            ):
                classification = "likely_duplicate"
        reviewed.append(
            {
                **candidate,
                "classification": classification,
                "reasons": reasons,
                "blocking": classification != "context_only",
                "distance_m": round(distance, 3),
            }
        )
    return reviewed
