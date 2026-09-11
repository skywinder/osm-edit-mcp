"""Bounded, cached Nominatim search. No editing API or OAuth is used."""

import asyncio
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from .config import config
from .discovery_errors import DiscoveryError, retry_after
from .discovery_models import LocationCandidate
from .http_client import get_public_client
from .nearby import validate_point


class NominatimExecutor:
    """One request/second per process, including failed requests; no auto retries.

    Multiple server processes must share an appropriately limited provider or
    gateway. Separate in-process limiters do not form a deployment-wide quota.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        client_factory: Callable[[], httpx.AsyncClient] = get_public_client,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self.endpoint = (endpoint or config.osm_nominatim_url).rstrip("/")
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Nominatim endpoint must be an HTTP(S) base URL without credentials"
            )
        self.client_factory, self.clock, self.wall_clock = (
            client_factory,
            clock,
            wall_clock,
        )
        self.sleep = sleep
        self.gate = asyncio.Semaphore(1)
        self.next_request = 0.0
        self.blocked_until = 0.0
        self.cache: OrderedDict[
            tuple[tuple[str, str], ...], tuple[float, list[dict[str, Any]]]
        ] = OrderedDict()

    async def search(self, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._search(params), timeout=15)
        except asyncio.TimeoutError as exc:
            raise DiscoveryError(
                "Geocoding timed out; retry later", "upstream_timeout", retryable=True
            ) from exc

    async def _search(self, params: dict[str, str]) -> list[dict[str, Any]]:
        key = tuple(sorted(params.items()))
        async with self.gate:
            cached = self.cache.get(key)
            if cached and cached[0] > self.clock():
                self.cache.move_to_end(key)
                return deepcopy(cached[1])
            remaining = self.blocked_until - self.clock()
            if remaining > 0:
                raise DiscoveryError(
                    "Geocoding is cooling down; retry later",
                    "rate_limited",
                    retryable=True,
                    retry_after_seconds=remaining,
                )
            await self.sleep(max(0, self.next_request - self.clock()))
            self.next_request = self.clock() + 1
            async with self.client_factory() as client:
                response = await client.get(
                    f"{self.endpoint}/search", params=params, timeout=10
                )
            delay = retry_after(response.headers.get("Retry-After"), self.wall_clock())
            if response.status_code in (429, 503):
                delay = delay if delay is not None else 60
                self.blocked_until = self.clock() + delay
                raise DiscoveryError(
                    "Geocoding provider is busy; retry later",
                    "rate_limited",
                    retryable=True,
                    retry_after_seconds=delay,
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or any(not isinstance(p, dict) for p in data):
                raise DiscoveryError(
                    "Invalid geocoding response", "invalid_upstream_response"
                )
            self.cache[key] = (self.clock() + 300, deepcopy(data))
            self.cache.move_to_end(key)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return data


def location_candidate(place: dict[str, Any]) -> LocationCandidate:
    """Keep provider ordering and importance; neither is a confidence score."""
    try:
        lat, lon = float(place["lat"]), float(place["lon"])
        validate_point(lat, lon)
        bbox = [float(n) for n in place.get("boundingbox", [])]
        if len(bbox) == 4:
            south, north, west, east = bbox
            bbox = [west, south, east, north]
        kind, identity = place.get("osm_type"), place.get("osm_id")
        valid_ref = (
            kind in ("node", "way", "relation")
            and isinstance(identity, int)
            and identity > 0
        )
        return {
            "place_ref": f"osm:{kind}:{identity}" if valid_ref else None,
            "display_name": str(place.get("display_name", "")),
            "location": {"lat": lat, "lon": lon},
            "bbox": bbox,
            "category": place.get("category", place.get("class")),
            "place_type": place.get("type"),
            "address": place.get("address", {}),
            "importance": float(place.get("importance", 0)),
            "osm_url": (
                f"https://www.openstreetmap.org/{kind}/{identity}"
                if valid_ref
                else None
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise DiscoveryError(
            "Invalid geocoding candidate", "invalid_upstream_response"
        ) from exc
