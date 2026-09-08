"""Normalize OSM facts and rank explicit preferences without inventing features."""

import re
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from opening_hours import OpeningHours, State

ATTRIBUTION = (
    "© OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright"
)


def language_code(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(
        r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", value
    ):
        raise ValueError("language must be a language code such as ru, en or pt-BR")
    return value


def evaluation_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("at_time must include a UTC offset or Z")
    return moment


def opening_state(
    hours: str | None,
    location: dict[str, float] | None,
    moment: datetime,
) -> Literal["open", "closed", "unknown"]:
    if not hours or len(hours) > 1024 or location is None:
        return "unknown"
    try:
        schedule = OpeningHours(
            hours, coords=(location["lat"], location["lon"]), max_interval_days=366
        )
        # The Rust binding accepts ZoneInfo, not datetime.timezone offsets.
        state, _comment = schedule.state(moment.astimezone(ZoneInfo("UTC")))
        # Unsupported calendars or ambiguous rules must never become a promise.
        if schedule.warnings:
            return "unknown"
        if state == State.OPEN:
            return "open"
        if state == State.CLOSED:
            return "closed"
        return "unknown"
    except Exception:
        # The extension also raises its own ParserError. One bad OSM tag must
        # not discard the other places or manufacture an open/closed answer.
        return "unknown"


def describe_place(
    place: dict[str, Any],
    preferred: dict[str, str],
    language: str | None,
    moment: datetime,
) -> dict[str, Any]:
    tags = place["tags"]
    names = [f"name:{language}", f"name:{language.split('-')[0]}"] if language else []
    place["name"] = next(
        (tags[k] for k in [*names, "name", "brand", "operator"] if tags.get(k)), None
    )
    place.update(
        source="openstreetmap",
        place_ref=f"osm:{place['type']}:{place['id']}",
        address={k[5:]: v for k, v in tags.items() if k.startswith("addr:")},
        website=tags.get("website") or tags.get("contact:website"),
        opening_hours=tags.get("opening_hours"),
        matched_reasons=[f"{k}={v}" for k, v in preferred.items() if tags.get(k) == v],
        unknown_features=[k for k in preferred if k not in tags],
    )
    place["preference_matches"] = len(place["matched_reasons"])
    place["open_status"] = opening_state(
        place["opening_hours"], place["location"], moment
    )
    if place["open_status"] == "unknown":
        place["unknown_features"].append("opening_hours")
    return place
