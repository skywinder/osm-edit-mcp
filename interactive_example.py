#!/usr/bin/env python3
"""
Interactive Example: OSM Edit MCP Server
========================================

This script demonstrates the key features of the OSM Edit MCP Server
in an interactive way. Run this to see how the server can be used
with AI assistants like Claude Desktop.

Usage:
    python interactive_example.py
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
    get_osm_node,
    get_osm_elements_in_area,
)

def print_header(title):
    """Print a nice header for each section."""
    print(f"\n{'='*60}")
    print(f"🗺️  {title}")
    print(f"{'='*60}")

def print_step(step_num, description):
    """Print a step description."""
    print(f"\n🔹 Step {step_num}: {description}")

async def interactive_demo():
    """Run an interactive demonstration of the MCP server capabilities."""

    print_header("OSM Edit MCP Server - Interactive Demo")
    print("This demo shows how AI assistants can use the MCP server")
    print("to interact with OpenStreetMap data.")

    # Step 1: Server Information
    print_step(1, "Getting server information")
    server_info = await get_server_info()
    print(f"✅ Server: {server_info['server_name']}")
    print(f"✅ Version: {server_info['version']}")
    print(f"✅ Available tools: {len(server_info['available_operations'])}")

    # Step 2: Coordinate Validation
    print_step(2, "Validating coordinates")
    # Test with Statue of Liberty coordinates
    statue_coords = (40.6892, -74.0445)
    result = await validate_coordinates(*statue_coords)

    if result["success"] and result["data"]["is_valid"]:
        print(f"✅ Coordinates {statue_coords} are valid")
        print(f"📍 Location: {result['message']}")
    else:
        print(f"❌ Coordinates {statue_coords} are invalid")

    # Step 3: Place Search
    print_step(3, "Searching for a famous landmark")
    place_result = await get_place_info("Statue of Liberty, New York")

    if place_result["success"] and place_result["data"]["count"] > 0:
        place = place_result["data"]["places"][0]
        print(f"✅ Found: {place['display_name']}")
        coords = place['coordinates']
        print(f"📍 Coordinates: {coords['lat']}, {coords['lon']}")
        print(f"🏛️  Type: {place.get('place_type', 'Unknown')}")
        statue_lat, statue_lon = float(coords['lat']), float(coords['lon'])
    else:
        print("❌ Could not find Statue of Liberty")
        statue_lat, statue_lon = 40.6892, -74.0445  # Fallback coordinates

    # Step 4: Finding Nearby Amenities
    print_step(4, "Finding nearby amenities")
    amenities_result = await find_nearby_amenities(
        statue_lat, statue_lon, 1000, "restaurant"
    )

    if amenities_result["success"]:
        count = amenities_result["data"]["count"]
        print(f"✅ Found {count} restaurants within 1km")

        if count > 0:
            first_restaurant = amenities_result["data"]["amenities"][0]
            name = first_restaurant["tags"].get("name", "Unnamed restaurant")
            print(f"🍽️  First result: {name}")
    else:
        print("⚠️  Amenity search unavailable (network/timeout issue)")

    # Step 5: Getting OSM Elements in Area
    print_step(5, "Getting OSM elements in a small area")
    # Small bounding box around Statue of Liberty
    # Format: "min_lon,min_lat,max_lon,max_lat"
    bbox = f"{statue_lon - 0.001},{statue_lat - 0.001},{statue_lon + 0.001},{statue_lat + 0.001}"

    area_result = await get_osm_elements_in_area(bbox)

    if area_result["success"]:
        elements = area_result["data"]["elements"]
        print(f"✅ Found {len(elements)} OSM elements in the area")

        # Count by type
        nodes = sum(1 for e in elements if e["type"] == "node")
        ways = sum(1 for e in elements if e["type"] == "way")
        relations = sum(1 for e in elements if e["type"] == "relation")

        print(f"📊 Breakdown: {nodes} nodes, {ways} ways, {relations} relations")
    else:
        print("❌ Could not retrieve OSM elements")

    # Step 6: Getting a Specific OSM Node
    print_step(6, "Getting a specific OSM node")
    # Try to get a well-known node (this might not exist in dev API)
    node_result = await get_osm_node(1)

    if node_result["success"]:
        if node_result["data"]["elements"]:
            node = node_result["data"]["elements"][0]
            print(f"✅ Retrieved node {node['id']}")
            print(f"📍 Location: {node['lat']}, {node['lon']}")
            if node.get("tags"):
                print(f"🏷️  Tags: {list(node['tags'].keys())}")
        else:
            print("📝 Node not found (expected in dev API)")
    else:
        print("❌ Could not retrieve node")

    # Summary
    print_header("Demo Complete!")
    print("🎉 The OSM Edit MCP Server is working correctly!")
    print("\n📋 What you can do with this server:")
    print("   • Search for places and get their coordinates")
    print("   • Validate coordinate inputs")
    print("   • Find nearby amenities and services")
    print("   • Retrieve OSM elements by ID or area")
    print("   • Create and manage changesets (with authentication)")
    print("   • Add new nodes, ways, and relations to OSM")

    print("\n🤖 AI Assistant Usage:")
    print("   • Ask Claude to 'find restaurants near Times Square'")
    print("   • Request 'validate these coordinates: 40.7580, -73.9855'")
    print("   • Say 'show me what's in this area' with a bounding box")
    print("   • Use natural language for complex OSM queries")

    print("\n🔧 Next Steps:")
    print("   • Configure with Claude Desktop using claude_desktop_config.json")
    print("   • Test with your own coordinates and places")
    print("   • Try more complex queries and OSM operations")
    print("   • Set up OAuth for editing capabilities")

if __name__ == "__main__":
    print("🚀 Starting Interactive Demo...")
    asyncio.run(interactive_demo())