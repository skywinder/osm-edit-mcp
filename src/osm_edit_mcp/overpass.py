"""Shared public Overpass transport; never rotates mirrors on rate limiting."""

import asyncio
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from .config import config
from .discovery_errors import DiscoveryError, retry_after
from .http_client import get_public_client


class OverpassExecutor:
    """Serialize requests, retry at most twice, cache only complete responses."""

    def __init__(
        self,
        endpoint: str | None = None,
        client_factory: Callable[[], httpx.AsyncClient] = get_public_client,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        wall_clock: Callable[[], float] = time.time,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = 30,
        cache_size: int = 32,
        total_timeout: float = 35,
    ) -> None:
        self.endpoint = endpoint or config.osm_overpass_url
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "Overpass endpoint must be an HTTP(S) URL without credentials"
            )
        self.client_factory = client_factory
        self.sleep, self.wall_clock, self.clock = sleep, wall_clock, clock
        self.ttl, self.cache_size = ttl, cache_size
        self.total_timeout = total_timeout
        self.cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.gate = asyncio.Semaphore(1)
        self.blocked_until = 0.0

    async def execute(self, query: str) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._execute(query), timeout=self.total_timeout
            )
        except asyncio.TimeoutError as exc:
            raise DiscoveryError(
                "Overpass time budget exceeded (including queue); retry later",
                "upstream_timeout",
                retryable=True,
            ) from exc

    async def _execute(self, query: str) -> dict[str, Any]:
        async with self.gate:
            cached = self.cache.get(query)
            if cached and cached[0] > self.clock():
                self.cache.move_to_end(query)
                return deepcopy(cached[1])
            remaining = self.blocked_until - self.clock()
            if remaining > 0:
                raise DiscoveryError(
                    "Overpass is cooling down; retry later",
                    "rate_limited",
                    retryable=True,
                    retry_after_seconds=remaining,
                )
            async with self.client_factory() as client:
                for attempt in range(3):
                    try:
                        response = await asyncio.wait_for(
                            client.post(
                                self.endpoint, data={"data": query}, timeout=30
                            ),
                            timeout=30,
                        )
                    except (httpx.TransportError, asyncio.TimeoutError):
                        if attempt == 2:
                            raise
                        await self.sleep(2**attempt)
                        continue
                    if response.status_code in (429, 502, 503, 504):
                        delay = float(2**attempt)
                        value = response.headers.get("Retry-After")
                        requested = retry_after(value, self.wall_clock())
                        if requested is not None:
                            delay = max(delay, requested)
                        # Persist the cooldown even when this call fails or is
                        # cancelled. A queued agent must not bypass Retry-After.
                        if requested is not None or response.status_code == 429:
                            self.blocked_until = max(
                                self.blocked_until, self.clock() + delay
                            )
                        # Do not shorten a server cooldown to fit our wait budget.
                        if delay > 30:
                            raise DiscoveryError(
                                f"Overpass Retry-After {value} exceeds the 30s "
                                "retry wait budget; retry later",
                                "rate_limited",
                                retryable=True,
                                retry_after_seconds=delay,
                            )
                        if attempt == 2:
                            response.raise_for_status()
                        await self.sleep(delay)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if (
                        not isinstance(data, dict)
                        or data.get("remark")
                        or not isinstance(data.get("elements"), list)
                    ):
                        raise DiscoveryError(
                            "Overpass returned an incomplete or invalid result; "
                            "retry later",
                            "invalid_upstream_response",
                            retryable=True,
                        )
                    self.cache[query] = (self.clock() + self.ttl, deepcopy(data))
                    self.cache.move_to_end(query)
                    while len(self.cache) > self.cache_size:
                        self.cache.popitem(last=False)
                    return data
        raise RuntimeError("Overpass retry budget exhausted")
