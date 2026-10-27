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
    "version": 2,
    "distance_method": "minimum distance between reviewed geometries; zero for overlap or containment",
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


def geometry_vertices(geometry: Dict[str, Any]) -> List[List[float]]:
    if geometry["type"] == "GeometryCollection":
        return [p for g in geometry["geometries"] for p in geometry_vertices(g)]
    if geometry["type"] == "Point":
        return [geometry["coordinates"]]
    if geometry["type"] == "LineString":
        return list(geometry["coordinates"])
    if geometry["type"] == "Polygon":
        return [p for ring in geometry["coordinates"] for p in ring]
    raise ValueError("Unsupported duplicate geometry")


def geometry_segments(
    geometry: Dict[str, Any],
) -> List[Tuple[List[float], List[float]]]:
    if geometry["type"] == "GeometryCollection":
        return [s for g in geometry["geometries"] for s in geometry_segments(g)]
    if geometry["type"] == "Point":
        return []
    rings = (
        geometry["coordinates"]
        if geometry["type"] == "Polygon"
        else [geometry["coordinates"]]
    )
    return [(a, b) for ring in rings for a, b in zip(ring, ring[1:])]


def segments_intersect(
    a: List[float], b: List[float], c: List[float], d: List[float]
) -> bool:
    origin = (a[1], a[0])
    aa, bb, cc, dd = (_xy(p, origin) for p in (a, b, c, d))

    def cross(
        p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]
    ) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on(
        p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]
    ) -> bool:
        return (
            min(p[0], q[0]) - 1e-8 <= r[0] <= max(p[0], q[0]) + 1e-8
            and min(p[1], q[1]) - 1e-8 <= r[1] <= max(p[1], q[1]) + 1e-8
        )

    ab_c, ab_d, cd_a, cd_b = (
        cross(aa, bb, cc),
        cross(aa, bb, dd),
        cross(cc, dd, aa),
        cross(cc, dd, bb),
    )
    if ((ab_c > 0 > ab_d) or (ab_d > 0 > ab_c)) and (
        (cd_a > 0 > cd_b) or (cd_b > 0 > cd_a)
    ):
        return True
    return any(
        abs(value) <= 1e-8 and on(p, q, r)
        for value, p, q, r in (
            (ab_c, aa, bb, cc),
            (ab_d, aa, bb, dd),
            (cd_a, cc, dd, aa),
            (cd_b, cc, dd, bb),
        )
    )


def geometries_distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Minimum distance, including crossing edges with no contained vertices."""
    av, bv = geometry_vertices(a), geometry_vertices(b)
    distances = [geometry_distance(b, (p[1], p[0])) for p in av]
    distances.extend(geometry_distance(a, (p[1], p[0])) for p in bv)
    if min(distances) == 0 or any(
        segments_intersect(p, q, r, s)
        for p, q in geometry_segments(a)
        for r, s in geometry_segments(b)
    ):
        return 0.0
    return min(distances)


def review_candidates(
    candidates: List[Dict[str, Any]], node: Dict[str, Any]
) -> List[Dict[str, Any]]:
    tags = node["tags"]
    point = (float(node["lat"]), float(node["lon"]))
    proposed_geometry = node.get(
        "geometry", {"type": "Point", "coordinates": [point[1], point[0]]}
    )
    names, contacts = _identities(tags)
    thresholds = POLICY.get(f"leisure={tags.get('leisure')}", POLICY["default"])
    reviewed = []
    for candidate in candidates:
        other = candidate["tags"]
        distance = geometries_distance(proposed_geometry, candidate["geometry"])
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
