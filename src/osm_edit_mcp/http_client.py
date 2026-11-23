"""HTTP client factories and outbound-query helpers."""

from typing import Any

import httpx
from anyio import CapacityLimiter
from anyio.lowlevel import RunVar

from .config import (
    DEVELOPMENT_API_BASE_URL,
    PRODUCTION_API_BASE_URL,
    USER_AGENT,
    config,
    logger,
)
from .token_store import load_oauth_token

_EDIT_API_HOSTS = {
    httpx.URL(base).host for base in (DEVELOPMENT_API_BASE_URL, PRODUCTION_API_BASE_URL)
}
_download_limiter: RunVar[CapacityLimiter] = RunVar("osm_edit_api_download_limiter")


class OSMHttpClient(httpx.AsyncClient):
    async def request(
        self, method: str, url: httpx.URL | str, **kwargs: Any
    ) -> httpx.Response:
        """Share the OSM editing API's two download slots across tool calls."""
        if method.upper() == "GET" and httpx.URL(url).host in _EDIT_API_HOSTS:
            limiter = _download_limiter.get(None)
            if limiter is None:
                limiter = CapacityLimiter(2)
                _download_limiter.set(limiter)
            async with limiter:
                return await super().request(method, url, **kwargs)
        return await super().request(method, url, **kwargs)


def get_authenticated_client() -> httpx.AsyncClient:
    """Get HTTP client with OAuth authentication if available"""
    config.assert_safe_api_target(config.current_api_base_url)
    token_data = None if config.api_environment == "custom" else load_oauth_token()
    if token_data and token_data.get("access_token"):
        headers = {
            "Authorization": f"Bearer {token_data['access_token']}",
            "User-Agent": USER_AGENT,
        }
        logger.debug("Using authenticated HTTP client")
        return OSMHttpClient(
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    else:
        logger.debug("Using unauthenticated HTTP client")
        return OSMHttpClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )


# Overpass queries declare [timeout:25] server-side and routinely take longer than
# httpx's 5s default, which surfaced as intermittent, blank-messaged ReadTimeouts.
PUBLIC_API_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def get_public_client() -> httpx.AsyncClient:
    """Get an unauthenticated HTTP client for public services (Overpass, Nominatim).

    Always sets a User-Agent: Overpass returns 406 without one.
    """
    return OSMHttpClient(
        headers={"User-Agent": USER_AGENT},
        timeout=PUBLIC_API_TIMEOUT,
    )


def describe_exception(exc: Exception) -> str:
    """Render an exception for the `error` field of a tool result.

    Several httpx timeout exceptions stringify to the empty string, which left
    callers with `"error": ""` and no way to tell what went wrong.
    """
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def overpass_literal(value: str) -> str:
    """Escape a value for use inside a double-quoted Overpass QL string.

    Without this, a search term containing a quote terminates the string early
    and the rest is interpreted as query syntax.
    """
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
