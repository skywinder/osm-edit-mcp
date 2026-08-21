"""Privacy-preserving adapter for a local Valhalla map-matching service."""

from typing import Any, Dict, List, Sequence, Tuple
from urllib.parse import urlparse

import httpx

from .config import config

Point = Tuple[float, float]


def _assert_local_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("Valhalla endpoint must be local to keep GPX data private")
    return url.rstrip("/")


def decode_polyline6(encoded: str) -> List[Point]:
    """Decode Valhalla's six-decimal encoded polyline into (lat, lon) points."""
    coordinates: List[Point] = []
    index = 0
    latitude = 0
    longitude = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            result = 0
            shift = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Invalid encoded Valhalla shape")
                value = ord(encoded[index]) - 63
                index += 1
                result |= (value & 0x1F) << shift
                shift += 5
                if value < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        coordinates.append((latitude / 1_000_000, longitude / 1_000_000))
    return coordinates


def _unmatched_spans(matched_points: Sequence[Dict[str, Any]]) -> List[Dict[str, int]]:
    spans: List[Dict[str, int]] = []
    start = None
    for index, point in enumerate(matched_points):
        match_type = str(point.get("type", "")).lower()
        matched = match_type not in {"unmatched", "0"} and (
            point.get("edge_index") is not None or match_type in {"matched", "1"}
        )
        if not matched and start is None:
            start = index
        elif matched and start is not None:
            spans.append({"start_point_index": start, "end_point_index": index - 1})
            start = None
    if start is not None:
        spans.append(
            {"start_point_index": start, "end_point_index": len(matched_points) - 1}
        )
    return spans


async def status() -> Dict[str, Any]:
    endpoint = _assert_local_endpoint(config.osm_valhalla_url)
    timeout = httpx.Timeout(config.osm_valhalla_timeout_seconds, connect=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{endpoint}/status")
        if response.status_code != 200:
            return {"available": False, "http_status": response.status_code}
        data = response.json()
        return {
            "available": True,
            "version": data.get("version"),
            "tileset_last_modified": data.get("tileset_last_modified"),
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "error": type(exc).__name__}


async def match_track(points: Sequence[Point], costing: str = "auto") -> Dict[str, Any]:
    if len(points) < 2:
        raise ValueError("Map matching requires at least two points")
    if costing not in {"auto", "bicycle", "pedestrian", "motor_scooter"}:
        raise ValueError("Unsupported Valhalla costing profile")
    endpoint = _assert_local_endpoint(config.osm_valhalla_url)
    request_points = list(points)
    if len(request_points) > 5_000:
        step = max(1, len(request_points) // 5_000)
        request_points = request_points[::step]
        if request_points[-1] != points[-1]:
            request_points.append(points[-1])

    request = {
        "shape": [{"lat": lat, "lon": lon} for lat, lon in request_points],
        "costing": costing,
        "shape_match": "map_snap",
        "filters": {
            "action": "include",
            "attributes": [
                "edge.osm_id",
                "edge.layer",
                "edge.bridge",
                "edge.tunnel",
                "edge.use",
                "matched.point",
                "matched.type",
                "matched.edge_index",
            ],
        },
    }
    timeout = httpx.Timeout(config.osm_valhalla_timeout_seconds, connect=2.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{endpoint}/trace_attributes", json=request)
    response.raise_for_status()
    data = response.json()
    matched_points = data.get("matched_points") or []
    spans = _unmatched_spans(matched_points)
    matched_count = max(
        0,
        len(matched_points)
        - sum(
            span["end_point_index"] - span["start_point_index"] + 1 for span in spans
        ),
    )
    encoded_shape = data.get("shape")
    matched_geometry = decode_polyline6(encoded_shape) if encoded_shape else []
    osm_way_ids = sorted(
        {
            int(edge["osm_id"])
            for edge in data.get("edges", [])
            if edge.get("osm_id") is not None
        }
    )
    return {
        "provider": "valhalla-local",
        "costing": costing,
        "input_point_count": len(points),
        "request_point_count": len(request_points),
        "matched_point_count": matched_count,
        "matched_percent": (
            round(100.0 * matched_count / len(matched_points), 1)
            if matched_points
            else 0.0
        ),
        "unmatched_spans": spans,
        "osm_way_ids": osm_way_ids,
        "matched_geometry": matched_geometry,
        "warnings": data.get("warnings", []),
    }


__all__ = ["decode_polyline6", "match_track", "status"]
