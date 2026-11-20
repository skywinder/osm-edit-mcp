"""Check guidance exposed to real MCP clients, not only Python docstrings."""

import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["full", "discovery"])
async def test_tagging_guidance_in_initialize_and_tool_metadata(profile):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from osm_edit_mcp.server import main; main()"],
        env={
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "OSM_TOOL_PROFILE": profile,
            "OSM_WRITE_PROFILE": "safe",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}

    if profile == "discovery":
        assert not result.instructions
        assert "preview_node_tag_edit" not in tools
    else:
        assert "drink:juice=yes" in result.instructions
        assert "not that it is freshly squeezed" in result.instructions
        assert "availability alone does not establish" in result.instructions
        assert "never use it for advertising" in result.instructions
        description = tools["preview_node_tag_edit"].description
        assert "drink:juice=yes" in description
        assert "preserve existing semicolon-separated cuisine values" in description
        assert "description neutral and non-redundant" in description
