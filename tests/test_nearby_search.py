"""Read-only search tests: all network responses are mocked fixtures."""

import asyncio
from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retry_after,delay",
    [("7", 7), (format_datetime(datetime.fromtimestamp(1007, timezone.utc)), 7)],
)
async def test_retry_after_stays_on_endpoint_and_is_bounded(retry_after, delay):
    from src.osm_edit_mcp.overpass import OverpassExecutor

    urls, sleeps = [], []

    async def sleep(seconds):
        sleeps.append(seconds)

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": retry_after})

    executor = OverpassExecutor(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
        sleep=sleep,
        wall_clock=lambda: 1000,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await executor.execute("busy")
    assert len(urls) == 3
    assert len(set(urls)) == 1
    assert sleeps == [delay, delay]


@pytest.mark.asyncio
async def test_cache_ttl_capacity_copy_and_concurrency():
    from src.osm_edit_mcp.overpass import OverpassExecutor

    calls, active, peak = [], 0, 0
    clock = [0]

    async def handler(request):
        nonlocal active, peak
        calls.append(request.content)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        active -= 1
        return httpx.Response(200, json={"elements": []})

    executor = OverpassExecutor(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
        clock=lambda: clock[0],
        ttl=10,
        cache_size=2,
    )
    first = await executor.execute("a")
    first["elements"].append("mutated")
    assert await executor.execute("a") == {"elements": []}
    assert len(calls) == 1
    clock[0] = 11
    await executor.execute("a")
    assert len(calls) == 2
    await asyncio.gather(*(executor.execute(str(i)) for i in range(5)))
    assert peak == 1
    assert len(executor.cache) == 2


@pytest.mark.asyncio
async def test_executor_rejects_partial_overpass_result():
    from src.osm_edit_mcp.overpass import OverpassExecutor

    executor = OverpassExecutor(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"elements": [], "remark": "runtime error: timeout"}
                )
            )
        )
    )
    with pytest.raises(ValueError, match="incomplete"):
        await executor.execute("partial")


@pytest.mark.asyncio
async def test_executor_posts_public_query():
    from src.osm_edit_mcp import overpass

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"elements": []})

    executor = overpass.OverpassExecutor(
        endpoint="https://example.test/interpreter",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
    )
    assert await executor.execute("query") == {"elements": []}
    assert requests[0].method == "POST"
    assert requests[0].url == "https://example.test/interpreter"
    assert "authorization" not in requests[0].headers


@pytest.mark.asyncio
async def test_nearby_categories_locations_distances_and_limit(monkeypatch):
    from src.osm_edit_mcp import read_tools

    queries = []

    async def fake(query):
        queries.append(query)
        return {
            "elements": [
                {
                    "type": "way",
                    "id": 2,
                    "center": {"lat": 0, "lon": 0.01},
                    "tags": {"leisure": "park"},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": 0,
                    "lon": 0,
                    "tags": {"tourism": "museum"},
                },
                {
                    "type": "relation",
                    "id": 3,
                    "center": {"lat": 0, "lon": 0.02},
                    "tags": {},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": 0,
                    "lon": 0,
                    "tags": {"tourism": "museum"},
                },
            ]
        }

    monkeypatch.setattr(read_tools, "execute_overpass", fake, raising=False)
    result = await read_tools.search_nearby_places(
        0, 0, categories=["museum", "park", "monument", "supermarket", "cafe"], limit=2
    )
    assert result["success"] is True
    data = result["data"]
    assert (data["total"], data["count"], data["truncated"]) == (3, 2, True)
    assert data["distance_type"] == "straight-line"
    assert [p["id"] for p in data["places"]] == [1, 2]
    assert data["places"][0]["distance_meters"] == 0
    assert data["places"][1]["distance_meters"] == pytest.approx(1111.951, abs=0.001)
    assert data["places"][1]["osm_url"] == "https://www.openstreetmap.org/way/2"
    for tag in [
        '"tourism"="museum"',
        '"leisure"="park"',
        '"historic"="monument"',
        '"shop"="supermarket"',
        '"amenity"="cafe"',
    ]:
        assert tag in queries[0]
    assert "nwr" in queries[0] and "out center tags;" in queries[0]
    assert "geom" not in queries[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"lat": float("nan")},
        {"lon": float("inf")},
        {"lat": True},
        {"radius_meters": 0},
        {"radius_meters": 10001},
        {"radius_meters": 2.5},
        {"limit": 0},
        {"limit": 101},
        {"categories": ["unknown"]},
        {"categories": []},
        {"tag_filters": {"name": "bad\nvalue"}},
    ],
)
async def test_invalid_nearby_never_queries(monkeypatch, kwargs):
    from src.osm_edit_mcp import read_tools

    async def forbidden(query):
        pytest.fail("invalid input reached network")

    monkeypatch.setattr(read_tools, "execute_overpass", forbidden)
    args = dict(lat=0, lon=0, categories=["museum"])
    args.update(kwargs)
    result = await read_tools.search_nearby_places(**args)
    assert result["success"] is False
    assert result["error"]
    if kwargs.get("categories") == ["unknown"]:
        assert "museum" in result["error"]


@pytest.mark.asyncio
async def test_exact_filters_and_missing_centers(monkeypatch):
    from src.osm_edit_mcp import read_tools

    queries = []

    async def fake(query):
        queries.append(query)
        return {"elements": [{"type": "relation", "id": 5, "tags": {}}]}

    monkeypatch.setattr(read_tools, "execute_overpass", fake)
    r = await read_tools.search_nearby_places(
        0, 0, categories=["hackerspace"], tag_filters={"name": 'A"B'}
    )
    assert r["success"]
    assert '["leisure"="hackerspace"]["name"="A\\"B"]' in queries[0]
    assert r["data"]["places"][0]["distance_meters"] is None
    assert r["data"]["places"][0]["location"] is None
    r = await read_tools.search_nearby_places(0, 0, tag_filters={"shop": "tea"})
    assert r["success"]


@pytest.mark.asyncio
async def test_transport_retry_and_large_cooldown():
    from src.osm_edit_mcp.overpass import OverpassExecutor

    calls, sleeps = [], []

    async def sleep(seconds):
        sleeps.append(seconds)

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ReadTimeout("mock timeout")
        return httpx.Response(200, json={"elements": []})

    ex = OverpassExecutor(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
        sleep=sleep,
    )
    assert await ex.execute("retry") == {"elements": []}
    assert sleeps == [1, 2]
    assert calls[0].extensions["timeout"]["read"] <= 30
    ex = OverpassExecutor(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, headers={"Retry-After": "300"})
            )
        ),
        sleep=sleep,
    )
    with pytest.raises(ValueError, match="Retry-After.*300"):
        await ex.execute("wait")


@pytest.mark.asyncio
async def test_legacy_radius_alias_and_scoped_text(monkeypatch):
    from src.osm_edit_mcp import read_tools, server

    queries = []

    async def fake(query):
        queries.append(query)
        return {"elements": []}

    monkeypatch.setattr(read_tools, "execute_overpass", fake)
    r = await read_tools.find_nearby_amenities(0, 0, radius=1200, amenity_type="cafe")
    assert r["success"] and r["data"]["radius_meters"] == 1200
    assert r["data"]["amenities"] == []
    assert "around:1200" in queries[-1]
    r = await read_tools.find_nearby_amenities(0, 0, radius_meters=1000, radius=1200)
    assert not r["success"] and "conflict" in r["error"].lower()
    before = len(queries)
    r = await read_tools.search_osm_elements("museum")
    assert not r["success"] and "bbox" in r["error"]
    assert len(queries) == before
    r = await read_tools.search_osm_elements(
        "A.*", "way", bbox="44.50,40.19,44.52,40.21"
    )
    assert r["success"]
    assert "(40.19,44.5,40.21,44.52)" in queries[-1]
    assert "way" in queries[-1] and "nwr" not in queries[-1]
    assert '[~".*"' not in queries[-1]
    assert "A\\\\.\\\\*" in queries[-1]
    assert r["data"]["distance_reference"] == "bbox_center"
    r = await read_tools.search_osm_elements("cafe", lat=0, lon=0, radius_meters=500)
    assert r["success"] and "around:500" in queries[-1]
    assert server.search_nearby_places is read_tools.search_nearby_places
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert tools["search_nearby_places"].annotations.readOnlyHint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"lat": 0},
        {"lat": 0, "lon": 0},
        {"bbox": "-180,-90,180,90"},
        {"bbox": "0,0,1,1"},
        {"bbox": "nan,0,1,1"},
        {"bbox": "2,0,1,1"},
        {"bbox": "0,0,0.1,0.1", "lat": 0},
        {"lat": 0, "lon": 0, "radius_meters": -1},
    ],
)
async def test_text_scope_validation(monkeypatch, scope):
    from src.osm_edit_mcp import read_tools

    async def forbidden(query):
        pytest.fail("invalid scope reached network")

    monkeypatch.setattr(read_tools, "execute_overpass", forbidden)
    r = await read_tools.search_osm_elements("cafe", **scope)
    assert not r["success"]


def test_configurable_overpass_endpoint(monkeypatch):
    from src.osm_edit_mcp.overpass import OverpassExecutor

    monkeypatch.setenv("OSM_OVERPASS_URL", "https://example.test/api/interpreter")
    assert OverpassExecutor().endpoint == "https://example.test/api/interpreter"
    monkeypatch.setenv("OSM_OVERPASS_URL", "file:///etc/passwd")
    with pytest.raises(ValueError, match="HTTP"):
        OverpassExecutor()


@pytest.mark.asyncio
async def test_geocode_without_scope_explicitly_skips_overpass(monkeypatch):
    from src.osm_edit_mcp import read_tools

    async def no_places(query):
        return {"success": True, "data": {"places": []}}

    async def forbidden(*args, **kwargs):
        pytest.fail("unbounded geocoder fallback")

    monkeypatch.setattr(read_tools, "get_place_info", no_places)
    monkeypatch.setattr(read_tools, "search_osm_elements", forbidden)
    r = await read_tools.smart_geocode("unresolved address")
    assert r["data"]["total_candidates"] == 0
    assert "bbox" in r["data"]["overpass_fallback"]


@pytest.mark.asyncio
async def test_web_search_passes_scope(monkeypatch):
    import web_server

    received = []

    async def fake(**kwargs):
        received.append(kwargs)
        return {"success": True, "data": {"elements": []}}

    monkeypatch.setattr(web_server, "search_osm_elements", fake)
    request = web_server.SearchRequest(
        query="museum", bbox="44.5,40.19,44.52,40.21", element_type="way", limit=7
    )
    await web_server.api_search_osm_elements(request, api_key="mock")
    assert received[0]["bbox"] == "44.5,40.19,44.52,40.21"
    assert received[0]["limit"] == 7
    assert received[0]["element_type"] == "way"


@pytest.mark.asyncio
async def test_queue_time_is_in_total_budget():
    from src.osm_edit_mcp.overpass import OverpassExecutor

    ex = OverpassExecutor(total_timeout=0.01)
    await ex.gate.acquire()
    try:
        with pytest.raises(ValueError, match="time budget"):
            await ex.execute("never sent")
    finally:
        ex.gate.release()
    assert ex.total_timeout < 180


@pytest.mark.asyncio
async def test_upstream_bad_coordinates_do_not_fabricate_distance(monkeypatch):
    from src.osm_edit_mcp import read_tools

    async def fake(query):
        return {
            "elements": [
                {"type": "node", "id": 1, "lat": float("nan"), "lon": 1},
                {"type": "way", "id": 2, "center": {"lat": 0, "lon": 0.01}},
            ]
        }

    monkeypatch.setattr(read_tools, "execute_overpass", fake)
    r = await read_tools.search_nearby_places(0, 0, categories=["museum"])
    assert r["success"]
    assert r["data"]["places"][-1]["distance_meters"] is None
    assert r["data"]["places"][-1]["location"] is None
    assert r["data"]["distance_reference"] == "query_location"
