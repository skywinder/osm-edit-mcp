"""Behavioral regressions for public place search; providers are mocked."""

import asyncio
from datetime import datetime, timezone
from typing import get_args
from unittest.mock import AsyncMock

import httpx
import pytest

from src.osm_edit_mcp import read_tools
from src.osm_edit_mcp.discovery_errors import DiscoveryError
from src.osm_edit_mcp.discovery_models import Category
from src.osm_edit_mcp.geocoding import NominatimExecutor
from src.osm_edit_mcp.nearby import CATEGORIES
from src.osm_edit_mcp.overpass import OverpassExecutor
from src.osm_edit_mcp.place_features import opening_state


def test_category_contract_covers_the_query_builder():
    assert set(get_args(Category)) == set(CATEGORIES)


@pytest.mark.asyncio
async def test_overpass_cooldown_survives_failure_and_allows_cached_results():
    now, calls = [0.0], []

    def handler(request):
        calls.append(request.content)
        if b"cached" in request.content:
            return httpx.Response(200, json={"elements": []})
        return httpx.Response(429, headers={"Retry-After": "300"})

    executor = OverpassExecutor(
        clock=lambda: now[0],
        ttl=600,
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    await executor.execute("cached")
    with pytest.raises(DiscoveryError):
        await executor.execute("first")
    now[0] = 20
    with pytest.raises(DiscoveryError) as raised:
        await executor.execute("different")
    assert raised.value.retry_after_seconds == 280
    assert await executor.execute("cached") == {"elements": []}
    assert len(calls) == 2
    now[0] = 301
    with pytest.raises(DiscoveryError):
        await executor.execute("after cooldown")
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_nominatim_serializes_caches_and_respects_cooldown():
    now, starts = [0.0], []

    async def sleep(delay):
        now[0] += delay

    def handler(request):
        starts.append(now[0])
        assert "authorization" not in request.headers
        if request.url.params["q"] == "busy":
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=[])

    executor = NominatimExecutor(
        clock=lambda: now[0],
        sleep=sleep,
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    await asyncio.gather(*(executor.search({"q": str(i)}) for i in range(3)))
    assert starts == [0, 1, 2]
    assert await executor.search({"q": "0"}) == []
    with pytest.raises(DiscoveryError):
        await executor.search({"q": "busy"})
    with pytest.raises(DiscoveryError) as raised:
        await executor.search({"q": "other"})
    assert raised.value.retry_after_seconds == 120
    assert len(starts) == 4


@pytest.mark.asyncio
async def test_preferences_do_not_turn_missing_tags_into_negative_facts(monkeypatch):
    mock = AsyncMock(
        return_value={
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 40.18,
                    "lon": 44.51,
                    "tags": {
                        "amenity": "cafe",
                        "name": "Local",
                        "opening_hours": "24/7",
                    },
                },
                {
                    "type": "node",
                    "id": 2,
                    "lat": 40.181,
                    "lon": 44.51,
                    "tags": {
                        "amenity": "cafe",
                        "name": "Other",
                        "name:ru": "Кафе",
                        "internet_access": "wlan",
                        "opening_hours": "24/7",
                    },
                },
                {
                    "type": "node",
                    "id": 3,
                    "lat": 40.18,
                    "lon": 44.51,
                    "tags": {"amenity": "cafe", "opening_hours": "24/7 off"},
                },
            ]
        }
    )
    monkeypatch.setattr(read_tools, "execute_overpass", mock)
    response = await read_tools.search_nearby_places(
        40.18,
        44.51,
        categories=["cafe"],
        preferred_tags={"internet_access": "wlan"},
        language="ru",
        open_now=True,
        at_time="2026-09-08T12:00:00+04:00",
    )
    data = response["data"]
    assert [p["id"] for p in data["places"]] == [2, 1]
    preferred, unknown = data["places"]
    assert preferred["name"] == "Кафе"
    assert preferred["matched_reasons"] == ["internet_access=wlan"]
    assert "internet_access" in unknown["unknown_features"]
    assert data["candidates_total"] == 3 and data["total"] == 2
    assert data["evaluated_at"] == "2026-09-08T12:00:00+04:00"
    assert (
        "internet_access" not in mock.await_args.args[0]
    )  # Preference is not a hard filter.


@pytest.mark.parametrize(
    "hours,expected",
    [
        (None, "unknown"),
        ("invalid hours", "unknown"),
        ("24/7", "open"),
        ("24/7 off", "closed"),
        ("Mo-Fr 10:00-18:00", "open"),
        ("Mo-Fr 10:00-18:00; Tu off", "closed"),
    ],
)
def test_opening_hours_uses_place_timezone_and_exceptions(hours, expected):
    # Tuesday 07:00 UTC is 11:00 at these coordinates, independent of server TZ.
    assert (
        opening_state(
            hours,
            {"lat": 40.18, "lon": 44.51},
            datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
        )
        == expected
    )


@pytest.mark.asyncio
async def test_details_preserve_public_source_even_when_edits_use_development(
    monkeypatch,
):
    monkeypatch.setattr(read_tools.config, "osm_use_dev_api", True)
    query = AsyncMock(
        return_value={
            "elements": [
                {
                    "type": "way",
                    "id": 17,
                    "center": {"lat": 40.18, "lon": 44.51},
                    "tags": {"leisure": "park"},
                }
            ]
        }
    )
    monkeypatch.setattr(read_tools, "execute_overpass", query)
    response = await read_tools.get_place_details("osm:way:17")
    assert response["success"]
    assert response["data"]["place"]["place_ref"] == "osm:way:17"
    assert response["data"]["place"]["source"] == "openstreetmap"
    assert response["data"]["place"]["distance_meters"] is None
    assert "way(17)" in query.await_args.args[0]


@pytest.mark.asyncio
async def test_geocoder_preserves_ambiguity_order_and_real_errors(monkeypatch):
    source = [
        {
            "lat": "40.18",
            "lon": "44.51",
            "osm_type": "node",
            "osm_id": i,
            "display_name": str(i),
            "category": "place",
            "type": "city",
            "importance": importance,
        }
        for i, importance in [(1, 0.1), (2, 0.9)]
    ]
    mock = AsyncMock(return_value=source)
    monkeypatch.setattr(read_tools._nominatim, "search", mock)
    resolved = await read_tools.resolve_location(
        "Город", language="ru", countrycodes=["AM"]
    )
    assert resolved["data"]["ambiguous"]
    assert [p["display_name"] for p in resolved["data"]["candidates"]] == ["1", "2"]
    assert mock.await_args.args[0]["format"] == "jsonv2"
    assert mock.await_args.args[0]["countrycodes"] == "am"
    old = await read_tools.smart_geocode("Город")
    assert old["data"]["best_match"]["display_name"] == "1"
    assert old["data"]["best_match"]["class"] == "place"
    assert "confidence" not in old["data"]["best_match"]
    mock.side_effect = DiscoveryError(
        "busy", "rate_limited", retryable=True, retry_after_seconds=60
    )
    failed = await read_tools.smart_geocode("Город")
    assert not failed["success"]
    assert failed["error_details"]["retry_after_seconds"] == 60
    mock.side_effect = None
    mock.return_value = []
    empty = await read_tools.resolve_location("Город")
    assert empty["success"] and empty["data"]["count"] == 0


@pytest.mark.asyncio
async def test_mcp_error_has_structured_retry_information(monkeypatch):
    from src.osm_edit_mcp.server import mcp

    monkeypatch.setattr(
        read_tools,
        "execute_overpass",
        AsyncMock(
            side_effect=DiscoveryError(
                "busy", "rate_limited", retryable=True, retry_after_seconds=120
            )
        ),
    )
    result = await mcp.call_tool(
        "search_nearby_places", {"lat": 0, "lon": 0, "categories": ["cafe"]}
    )
    assert result.isError
    assert result.structuredContent["error_details"]["code"] == "rate_limited"
    assert result.structuredContent["error_details"]["retry_after_seconds"] == 120
