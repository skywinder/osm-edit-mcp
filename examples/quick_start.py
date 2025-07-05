#!/usr/bin/env python3
"""
Quick Start Example for OSM Edit MCP Server

This example demonstrates basic usage of the OSM Edit MCP Server.
Make sure the server is running before executing this script.
"""

import asyncio
import json
from typing import Dict, Any

# Note: In real usage, you would connect to the MCP server through the MCP protocol
# This example shows the expected inputs and outputs for each operation


async def example_read_operations():
    """Demonstrate read-only operations."""
    print("=== Read Operations Examples ===\n")
    
    # Example 1: Get server information
    print("1. Get Server Info")
    server_info = {
        "tool": "get_server_info",
        "expected_output": {
            "success": True,
            "data": {
                "version": "0.1.0",
                "api_mode": "Development",
                "api_base_url": "https://api06.dev.openstreetmap.org/api/0.6",
                "authenticated": True,
                "username": "your_username"
            }
        }
    }
    print(f"Output: {json.dumps(server_info['expected_output'], indent=2)}\n")
    
    # Example 2: Validate coordinates
    print("2. Validate Coordinates (London)")
    validate_coords = {
        "tool": "validate_coordinates",
        "input": {"lat": 51.5074, "lon": -0.1278},
        "expected_output": {
            "success": True,
            "data": {
                "valid": True,
                "location": {
                    "display_name": "London, Greater London, England, United Kingdom",
                    "lat": 51.5074,
                    "lon": -0.1278
                }
            }
        }
    }
    print(f"Input: {validate_coords['input']}")
    print(f"Output: {json.dumps(validate_coords['expected_output'], indent=2)}\n")
    
    # Example 3: Find nearby amenities
    print("3. Find Nearby Restaurants")
    find_amenities = {
        "tool": "find_nearby_amenities",
        "input": {
            "lat": 51.5074,
            "lon": -0.1278,
            "radius": 500,
            "amenity_type": "restaurant"
        },
        "expected_output": {
            "success": True,
            "data": {
                "center": {"lat": 51.5074, "lon": -0.1278},
                "radius": 500,
                "amenity_type": "restaurant",
                "results": [
                    {
                        "name": "Example Restaurant",
                        "type": "restaurant",
                        "distance": 120.5,
                        "tags": {"cuisine": "italian", "opening_hours": "Mo-Su 11:00-23:00"}
                    }
                ]
            }
        }
    }
    print(f"Input: {find_amenities['input']}")
    print(f"Output: {json.dumps(find_amenities['expected_output'], indent=2)}\n")


async def example_natural_language():
    """Demonstrate natural language processing."""
    print("=== Natural Language Examples ===\n")
    
    # Example: Parse natural language request
    print("1. Parse Natural Language Request")
    nl_request = {
        "tool": "parse_natural_language_osm_request",
        "input": {"request": "Find coffee shops near the Tower of London that are open now"},
        "expected_output": {
            "success": True,
            "data": {
                "parsed_request": {
                    "action": "search",
                    "object_type": "coffee shops",
                    "location": "Tower of London",
                    "filters": ["open now"]
                },
                "suggested_tags": {
                    "amenity": "cafe",
                    "opening_hours": "*"
                }
            }
        }
    }
    print(f"Input: {nl_request['input']}")
    print(f"Output: {json.dumps(nl_request['expected_output'], indent=2)}\n")


async def example_write_operations():
    """Demonstrate write operations (requires authentication)."""
    print("=== Write Operations Examples (Requires Auth) ===\n")
    
    # Example 1: Create a changeset
    print("1. Create Changeset")
    create_changeset = {
        "tool": "create_changeset",
        "input": {"comment": "Adding a new cafe via OSM Edit MCP"},
        "expected_output": {
            "success": True,
            "data": {
                "changeset_id": 12345,
                "created_by": "your_username",
                "api_url": "https://api06.dev.openstreetmap.org/api/0.6/changeset/12345"
            }
        }
    }
    print(f"Input: {create_changeset['input']}")
    print(f"Output: {json.dumps(create_changeset['expected_output'], indent=2)}\n")
    
    # Example 2: Create a node
    print("2. Create OSM Node (Cafe)")
    create_node = {
        "tool": "create_osm_node",
        "input": {
            "lat": 51.5074,
            "lon": -0.1278,
            "tags": {
                "name": "Example Cafe",
                "amenity": "cafe",
                "opening_hours": "Mo-Fr 07:00-18:00; Sa-Su 08:00-17:00"
            },
            "changeset_id": 12345
        },
        "expected_output": {
            "success": True,
            "data": {
                "node_id": 987654321,
                "version": 1,
                "changeset_id": 12345
            }
        }
    }
    print(f"Input: {create_node['input']}")
    print(f"Output: {json.dumps(create_node['expected_output'], indent=2)}\n")


def main():
    """Run all examples."""
    print("OSM Edit MCP Server - Quick Start Examples")
    print("=" * 50)
    print("\nThese examples show the expected inputs and outputs")
    print("for common operations with the OSM Edit MCP Server.\n")
    
    # Run examples
    asyncio.run(example_read_operations())
    asyncio.run(example_natural_language())
    asyncio.run(example_write_operations())
    
    print("\nFor actual usage:")
    print("1. Start the MCP server: python main.py")
    print("2. Connect via MCP client (e.g., Claude Desktop)")
    print("3. Use the tools shown above\n")


if __name__ == "__main__":
    main()