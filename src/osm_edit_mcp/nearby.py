"""Pure query and result helpers for bounded read-only place searches."""

import math
from datetime import datetime, timezone
from typing import Any

from .http_client import overpass_literal
from .place_features import ATTRIBUTION, describe_place


def validate_point(lat: Any, lon: Any) -> None:
    for value, bound in ((lat, 90), (lon, 180)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not -bound <= value <= bound
        ):
            raise ValueError(
                "Invalid coordinates: finite latitude [-90,90] "
                "and longitude [-180,180] required"
            )


def bounded_integer(value: Any, name: str, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")


def safe_text(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 255
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError(
            "Tag/query text must be nonempty, at most 255 characters, "
            "without control characters"
        )
    return overpass_literal(value)


def selectors(
    categories: list[str] | None, tag_filters: dict[str, str] | None
) -> list[str]:
    if categories is not None and (
        not isinstance(categories, list) or len(categories) > 20
    ):
        raise ValueError("categories must be a list of at most 20 names")
    if any(not isinstance(n, str) or n not in CATEGORIES for n in categories or []):
        raise ValueError(
            "Unknown category. Available: " + ", ".join(sorted(CATEGORIES))
        )
    if tag_filters is not None and (
        not isinstance(tag_filters, dict) or len(tag_filters) > 10
    ):
        raise ValueError(
            "tag_filters must be a dictionary of at most 10 exact key/value pairs"
        )
    filters = "".join(
        f'["{safe_text(k)}"="{safe_text(v)}"]'
        for k, v in sorted((tag_filters or {}).items())
    )
    if not categories and not filters:
        raise ValueError(
            "Supply categories or exact tag_filters. Available: "
            + ", ".join(sorted(CATEGORIES))
        )
    groups = [CATEGORIES[n] for n in sorted(set(categories or []))] or [{}]
    return [
        "".join(f'["{k}"="{v}"]' for k, v in group.items()) + filters
        for group in groups
    ]


CATEGORIES = {
    **{
        name: {"amenity": name}
        for name in (
            "restaurant",
            "cafe",
            "bar",
            "pub",
            "hospital",
            "pharmacy",
            "bank",
            "atm",
            "toilets",
            "drinking_water",
            "school",
            "library",
            "parking",
            "place_of_worship",
        )
    },
    **{
        name: {"tourism": name}
        for name in (
            "museum",
            "gallery",
            "attraction",
            "viewpoint",
            "hotel",
            "hostel",
            "information",
            "artwork",
        )
    },
    **{
        name: {"leisure": name}
        for name in (
            "hackerspace",
            "park",
            "garden",
            "playground",
            "sports_centre",
            "swimming_pool",
        )
    },
    **{
        name: {"historic": name}
        for name in ("monument", "memorial", "castle", "ruins", "archaeological_site")
    },
    **{
        name: {"shop": name}
        for name in ("supermarket", "convenience", "bakery", "books", "clothes")
    },
}


def results(
    data: dict[str, Any],
    lat: float,
    lon: float,
    limit: int,
    *,
    preferred_tags: dict[str, str] | None = None,
    language: str | None = None,
    open_now: bool = False,
    moment: datetime | None = None,
) -> dict[str, Any]:
    moment = moment or datetime.now(timezone.utc)
    unique = {}
    for element in data["elements"]:
        kind, identity = element["type"], element["id"]
        location = element if kind == "node" else element.get("center", {})
        latitude, longitude = location.get("lat"), location.get("lon")
        distance = None
        try:
            validate_point(latitude, longitude)
        except ValueError:
            latitude, longitude = None, None
        if latitude is not None and longitude is not None:
            a, b = math.radians(lat), math.radians(latitude)
            h = (
                math.sin((b - a) / 2) ** 2
                + math.cos(a)
                * math.cos(b)
                * math.sin(math.radians(longitude - lon) / 2) ** 2
            )
            distance = 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))
        unique[(kind, identity)] = describe_place(
            {
                "type": kind,
                "id": identity,
                "tags": element.get("tags", {}),
                "location": (
                    {"lat": latitude, "lon": longitude}
                    if distance is not None
                    else None
                ),
                "location_source": "node" if kind == "node" else "overpass_bbox_center",
                "distance_meters": round(distance, 3) if distance is not None else None,
                "osm_url": f"https://www.openstreetmap.org/{kind}/{identity}",
            },
            preferred_tags or {},
            language,
            moment,
        )
    candidates_total = len(unique)
    unknown_hours = sum(p["open_status"] == "unknown" for p in unique.values())
    places = sorted(
        (p for p in unique.values() if not open_now or p["open_status"] == "open"),
        key=lambda p: (
            -p["preference_matches"],
            p["distance_meters"] is None,
            p["distance_meters"] or 0,
            p["type"],
            p["id"],
        ),
    )
    return {
        "places": places[:limit],
        "total": len(places),
        "count": len(places[:limit]),
        "truncated": len(places) > limit,
        "distance_type": "straight-line",
        "attribution": ATTRIBUTION,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "evaluated_at": moment.isoformat(),
        "candidates_total": candidates_total,
        "unknown_opening_hours": unknown_hours,
    }
