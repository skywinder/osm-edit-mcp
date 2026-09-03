#!/usr/bin/env python3
"""Run a real, read-only MCP protocol smoke test against the released server.

The example starts `uvx osm-edit-mcp` over stdio, completes MCP initialization,
checks that `get_server_info` is annotated read-only, and calls only that tool.
It never authenticates, opens a changeset, or invokes a mutation tool.
"""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

READ_ONLY_TOOL = "get_server_info"


async def smoke_test() -> None:
    """Initialize the server and call one local read-only capability tool."""
    server = StdioServerParameters(
        command="uvx",
        args=["osm-edit-mcp"],
        env={
            "OSM_USE_DEV_API": "true",
            "OSM_WRITE_PROFILE": "safe",
            "OSM_REQUIRE_HOST_CONFIRMATION": "true",
        },
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}

            tool = tools.get(READ_ONLY_TOOL)
            if tool is None:
                raise RuntimeError(f"{READ_ONLY_TOOL!r} was not registered")
            if tool.annotations is None or tool.annotations.readOnlyHint is not True:
                raise RuntimeError(f"{READ_ONLY_TOOL!r} is not marked read-only")

            result = await session.call_tool(READ_ONLY_TOOL, {})
            if result.isError:
                raise RuntimeError(f"{READ_ONLY_TOOL!r} returned an MCP error")

            print(f"Initialized OSM Edit MCP with {len(tools)} tools.")
            print(f"Called read-only tool: {READ_ONLY_TOOL}")
            for content in result.content:
                if isinstance(content, TextContent):
                    print(content.text)
                else:
                    print(content.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(smoke_test())
