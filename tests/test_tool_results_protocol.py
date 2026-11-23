"""Check how a stdio host sees successful and failed editing tool calls."""

import json
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_edit_tools_report_domain_failures_and_preserve_result_shape(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from osm_edit_mcp.server import main; main()"],
        env={
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "OSM_TOOL_PROFILE": "full",
            "OSM_USE_DEV_API": "true",
            "OSM_WRITE_PROFILE": "safe",
            "OSM_PROPOSAL_DB_PATH": str(tmp_path / "proposals.sqlite3"),
            "USE_KEYRING": "false",
            "LOG_LEVEL": "ERROR",
        },
    )
    gpx = '<gpx><trk><trkseg><trkpt lat="1" lon="2"/></trkseg></trk></gpx>'
    with anyio.fail_after(60):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for name, args, expected_error in [
                    ("analyze_gpx_track", {}, "ValueError"),
                    (
                        "apply_osm_edit",
                        {"proposal_id": "missing", "proposal_digest": "missing"},
                        "Unknown or expired proposal",
                    ),
                    ("analyze_gpx_track", {"gpx_xml": gpx}, None),
                ]:
                    result = await session.call_tool(name, args)
                    payload = json.loads(result.content[0].text)
                    assert result.structuredContent == {"result": payload}
                    assert result.isError is (expected_error is not None)
                    assert payload["success"] is (expected_error is None)
                    if expected_error is not None:
                        assert payload["error"] == expected_error
                    else:
                        assert payload["data"]["segment_count"] == 1
