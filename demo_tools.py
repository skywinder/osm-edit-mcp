#!/usr/bin/env python3
"""
OSM Edit MCP Server - Tool Demonstration
=========================================

This script demonstrates how to use the various tools provided by the OSM Edit MCP server.
Run this to see examples of each tool in action.
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import (
    get_server_info,
    validate_coordinates,
    get_place_info,
    find_nearby_amenities,
    search_osm_elements,
    get_osm_node,
)

async def demo_server_info():
    """Demonstrate server information tool."""
    print("🖥️  Server Information")
    print("=" * 50)

    result = await get_server_info()
    print(f"Server: {result['server_name']}")
    print(f"Version: {result['version']}")
    print(f"API Base URL: {result['api_base_url']}")
    print(f"Available Tools: {len(result['available_operations'])}")
    print()

async def demo_coordinate_validation():
    """Demonstrate coordinate validation tool."""
    print("🌍 Coordinate Validation")
    print("=" * 50)

    # Test famous locations
    locations = [
        (40.7580, -73.9855, "Times Square, New York"),
        (51.5074, -0.1278, "London, UK"),
        (48.8584, 2.2945, "Eiffel Tower, Paris"),
        (35.6762, 139.6503, "Tokyo, Japan"),
        (999, 999, "Invalid coordinates"),
    ]

    for lat, lon, description in locations:
        result = await validate_coordinates(lat, lon)
        if result["success"]:
            print(f"✓ {description}")
            print(f"  Coordinates: {lat}, {lon}")
            print(f"  Valid: {result['data']['is_valid']}")
            if result['data']['is_valid']:
                print(f"  Location: {result['data']['location_info']['display_name']}")
        else:
            print(f"✗ {description}")
            print(f"  Error: {result['error']}")
        print()

async def demo_place_search():
    """Demonstrate place search tool."""
    print("🔍 Place Search")
    print("=" * 50)

    places = [
        "Central Park, New York",
        "Big Ben, London",
        "Sydney Opera House",
        "Nonexistent Place XYZ123",
    ]

    for place_name in places:
        result = await get_place_info(place_name)
        if result["success"] and result["data"]["places"]:
            place = result["data"]["places"][0]
            print(f"✓ Found: {place_name}")
            print(f"  Display Name: {place['display_name']}")
            print(f"  Coordinates: {place['coordinates']['lat']}, {place['coordinates']['lon']}")
            print(f"  Type: {place.get('type', place.get('class', 'Unknown'))}")
        else:
            print(f"✗ Not found: {place_name}")
        print()

async def demo_nearby_amenities():
    """Demonstrate nearby amenities search."""
    print("🏪 Nearby Amenities")
    print("=" * 50)

    # Search for restaurants near Times Square
    lat, lon = 40.7580, -73.9855
    print(f"Searching for restaurants near Times Square ({lat}, {lon})...")

    result = await find_nearby_amenities(lat, lon, 500, "restaurant")
    if result["success"]:
        amenities = result["data"]["amenities"]
        print(f"✓ Found {len(amenities)} restaurants within 500m")
        for i, amenity in enumerate(amenities[:3]):  # Show first 3
            print(f"  {i+1}. {amenity['tags'].get('name', 'Unnamed')}")
            print(f"     Type: {amenity['tags'].get('amenity', 'Unknown')}")
            print(f"     Distance: ~{amenity.get('distance', 'unknown')}m")
            if 'cuisine' in amenity['tags']:
                print(f"     Cuisine: {amenity['tags']['cuisine']}")
        if len(amenities) > 3:
            print(f"  ... and {len(amenities) - 3} more")
    else:
        print(f"✗ Error searching for restaurants: {result['error']}")
    print()

async def demo_element_search():
    """Demonstrate OSM element search."""
    print("🔎 OSM Element Search")
    print("=" * 50)

    queries = [
        ("coffee shop", "node"),
        ("park", "way"),
        ("subway station", "node"),
    ]

    for query, element_type in queries:
        print(f"Searching for '{query}' ({element_type})...")
        result = await search_osm_elements(query, element_type)
        if result["success"]:
            elements = result["data"]["elements"]
            print(f"✓ Found {len(elements)} {element_type}s")
            for i, element in enumerate(elements[:2]):  # Show first 2
                name = element.get("tags", {}).get("name", "Unnamed")
                print(f"  {i+1}. {name}")
                if "lat" in element and "lon" in element:
                    print(f"     Location: {element['lat']}, {element['lon']}")
        else:
            print(f"✗ Error searching: {result['error']}")
        print()

async def demo_osm_node():
    """Demonstrate OSM node retrieval."""
    print("🏛️  OSM Node Retrieval")
    print("=" * 50)

    # Try to get a well-known node (this might not exist in dev API)
    node_id = 26734748  # Example node ID
    print(f"Attempting to get OSM node {node_id}...")

    result = await get_osm_node(node_id)
    if result["success"]:
        node = result["data"]["elements"][0]
        print(f"✓ Successfully retrieved node {node_id}")
        print(f"  Location: {node['lat']}, {node['lon']}")
        print(f"  Tags: {node.get('tags', {})}")
    else:
        print(f"✗ Could not retrieve node {node_id}: {result['error']}")
        print("  (This is expected when using the development API)")
    print()

async def main():
    """Run all demonstrations."""
    print("🚀 OSM Edit MCP Server - Tool Demonstration")
    print("=" * 60)
    print()

    try:
        await demo_server_info()
        await demo_coordinate_validation()
        await demo_place_search()
        await demo_nearby_amenities()
        await demo_element_search()
        await demo_osm_node()

        print("🎉 Demonstration completed successfully!")
        print()
        print("💡 Next Steps:")
        print("  1. Configure with Claude Desktop using claude_desktop_config.json")
        print("  2. Try asking Claude to find nearby restaurants, validate coordinates, etc.")
        print("  3. Explore the 13 available tools with natural language queries")
        print()
        print("📚 See README.md for more examples and usage instructions.")

    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())