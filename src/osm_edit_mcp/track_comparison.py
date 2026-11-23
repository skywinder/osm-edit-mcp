"""Bounded, orientation-independent distances between selected survey lines."""

import math
from dataclasses import dataclass
from typing import Sequence

EARTH_RADIUS_M = 6_371_008.8
SAMPLE_SPACING_M = 20
# Bound both the GeoJSON returned over stdio and the number of distance checks.
MAX_OVERLAY_POINTS = 1_500
MAX_DISTANCE_CHECKS = 1_000_000
Vector = tuple[float, float, float]


@dataclass(frozen=True)
class Segment:
    start: Vector
    delta: Vector
    squared_length: float
    steps: int


def _cartesian(lat: float, lon: float) -> Vector:
    lat, lon = math.radians(lat), math.radians(lon)
    radius = EARTH_RADIUS_M * math.cos(lat)
    return (
        radius * math.cos(lon),
        radius * math.sin(lon),
        EARTH_RADIUS_M * math.sin(lat),
    )


def _segments(points: Sequence[tuple[float, float]]) -> list[Segment]:
    vertices = [_cartesian(lat, lon) for lat, lon in points]
    segments = []
    for start, end in zip(vertices, vertices[1:]):
        delta = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        squared = sum(d * d for d in delta)
        segments.append(
            Segment(
                start,
                delta,
                squared,
                max(1, math.ceil(math.sqrt(squared) / SAMPLE_SPACING_M)),
            )
        )
    return segments


def _nearest_distance(point: Vector, segments: list[Segment]) -> float:
    # Compare in Earth-centred coordinates. Each continuous GPX leg is at most
    # 500 m, so its chord deviates from the surface by less than 5 mm.
    best = math.inf
    for segment in segments:
        x = point[0] - segment.start[0]
        y = point[1] - segment.start[1]
        z = point[2] - segment.start[2]
        dx, dy, dz = segment.delta
        t = (
            (x * dx + y * dy + z * dz) / segment.squared_length
            if segment.squared_length
            else 0.0
        )
        t = min(1.0, max(0.0, t))
        x, y, z = x - t * dx, y - t * dy, z - t * dz
        best = min(best, x * x + y * y + z * z)
    return (
        2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(best) / (2 * EARTH_RADIUS_M)))
    )


def _directed_distances(
    source: list[Segment], target: list[Segment]
) -> tuple[float, float]:
    previous = _nearest_distance(source[0].start, target)
    maximum, weighted_sum, length = previous, 0.0, 0.0
    for segment in source:
        step_length = math.sqrt(segment.squared_length) / segment.steps
        x, y, z = segment.start
        dx, dy, dz = segment.delta
        for index in range(1, segment.steps + 1):
            fraction = index / segment.steps
            distance = _nearest_distance(
                (x + fraction * dx, y + fraction * dy, z + fraction * dz), target
            )
            maximum = max(maximum, distance)
            weighted_sum += (previous + distance) * 0.5 * step_length
            length += step_length
            previous = distance
    return (weighted_sum / length if length else previous), maximum


def pairwise_distances(
    lines: Sequence[Sequence[tuple[float, float]]], ids: list[str]
) -> list[dict]:
    if sum(map(len, lines)) > MAX_OVERLAY_POINTS:
        raise ValueError(
            f"Comparison overlay exceeds {MAX_OVERLAY_POINTS} total points; select shorter ranges"
        )
    traces = [_segments(line) for line in lines]
    samples = [1 + sum(segment.steps for segment in trace) for trace in traces]
    pairs = [(i, j) for i in range(len(lines)) for j in range(i + 1, len(lines))]
    checks = sum(
        samples[i] * len(traces[j]) + samples[j] * len(traces[i]) for i, j in pairs
    )
    if checks > MAX_DISTANCE_CHECKS:
        raise ValueError(
            "Comparison is too large at 20 m sampling intervals; select fewer or shorter ranges"
        )
    results = []
    for i, j in pairs:
        forward_mean, forward_max = _directed_distances(traces[i], traces[j])
        reverse_mean, reverse_max = _directed_distances(traces[j], traces[i])
        results.append(
            {
                "selection_ids": [ids[i], ids[j]],
                "mean_distance_m": round((forward_mean + reverse_mean) * 0.5, 2),
                "max_distance_m": round(max(forward_max, reverse_max), 2),
            }
        )
    return results
