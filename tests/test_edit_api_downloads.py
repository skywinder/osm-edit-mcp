"""The editing API allows two download threads for an application."""

import asyncio

import httpx
import pytest

from osm_edit_mcp.http_client import OSMHttpClient


@pytest.mark.asyncio
async def test_concurrent_edit_api_reads_share_download_slots():
    active = peak = 0

    async def respond(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200)

    async with (
        OSMHttpClient(transport=httpx.MockTransport(respond)) as first,
        OSMHttpClient(transport=httpx.MockTransport(respond)) as second,
    ):
        clients = [first, second] * 4
        responses = await asyncio.gather(
            *(
                client.get("https://api.openstreetmap.org/api/0.6/map")
                for client in clients
            )
        )
        assert all(response.is_success for response in responses)
        assert peak == 2
