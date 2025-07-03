#!/usr/bin/env python3
"""
Simple test script for the OSM Edit MCP Server
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import mcp

async def test_server():
    """Test that the MCP server is properly configured"""
    print("Testing OSM Edit MCP Server...")

    # Get list of tools
    tools = await mcp.list_tools()
    print(f"✓ Found {len(tools)} tools:")

    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")

    print("\n✓ Server is properly configured!")
    print("Ready to use with Claude Desktop or other MCP clients.")

    return True

if __name__ == "__main__":
    try:
        asyncio.run(test_server())
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)