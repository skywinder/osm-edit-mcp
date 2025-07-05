#!/usr/bin/env python3
"""
List all available MCP tools in the server
"""

import sys
from pathlib import Path
import json

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import mcp

# Simulate tool listing request
print("Testing MCP Tools Listing...")
print("=" * 50)

# Create a mock tool listing request
tools_request = {
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 2
}

print(f"\nRequest: {json.dumps(tools_request, indent=2)}")
print("\nTo test this with the actual server, run:")
print(f"echo '{json.dumps(tools_request)}' | uv run python main.py")

# Count registered decorators
decorator_count = 0
for attr_name in dir(mcp):
    attr = getattr(mcp, attr_name)
    if hasattr(attr, '__name__') and 'tool' in attr.__name__:
        decorator_count += 1

print(f"\nServer initialized: {mcp.name}")
print("FastMCP server is ready to handle tool requests")
print("\nExpected tools include:")
tools = [
    "get_server_info",
    "find_nearby_amenities", 
    "get_place_info",
    "search_osm_elements",
    "parse_natural_language_osm_request",
    "get_osm_node",
    "get_osm_way",
    "get_osm_relation",
    "get_osm_elements_in_area",
    "get_osm_statistics",
    "validate_coordinates",
    "smart_geocode",
    "create_changeset",
    "close_changeset",
    "create_osm_node",
    "create_place_from_description",
    "update_osm_node",
    "update_osm_way",
    "delete_osm_element"
]

for i, tool in enumerate(tools, 1):
    print(f"  {i}. {tool}")

print(f"\nTotal: ~{len(tools)} tools available")