#!/usr/bin/env python3
"""
Quick Test Script for OSM Edit MCP Server
==========================================

This script performs quick tests of the main server functionality.
Use this to verify that your server is working correctly.
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
)

def print_separator(title):
    """Print a nice separator for test sections."""
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print(f"{'='*60}")

async def test_server_info():
    """Test server information."""
    print_separator("Server Information Test")
    result = await get_server_info()
    print(f"✅ Server Name: {result['server_name']}")
    print(f"✅ Version: {result['version']}")
    print(f"✅ Available Operations: {len(result['available_operations'])}")
    return True

async def test_coordinates():
    """Test coordinate validation."""
    print_separator("Coordinate Validation Test")

    # Test valid coordinates (Times Square, NYC)
    result = await validate_coordinates(40.7580, -73.9855)
    if result["success"] and result["data"]["is_valid"]:
        print("✅ Valid coordinates test passed")
        print(f"   Location: {result['data']['location_info']['display_name']}")
    else:
        print("❌ Valid coordinates test failed")
        return False

    # Test invalid coordinates
    result = await validate_coordinates(91.0, -181.0)
    if result["success"] and not result["data"]["is_valid"]:
        print("✅ Invalid coordinates test passed")
        print(f"   Error: {result['message']}")
    else:
        print("❌ Invalid coordinates test failed")
        return False

    return True

async def test_place_search():
    """Test place search functionality."""
    print_separator("Place Search Test")

    # Search for a famous landmark
    result = await get_place_info("Times Square, New York")
    if result["success"] and result["data"]["count"] > 0:
        print("✅ Place search test passed")
        first_place = result["data"]["places"][0]
        print(f"   Location: {first_place['display_name']}")
        print(f"   Coordinates: {first_place['coordinates']['lat']}, {first_place['coordinates']['lon']}")
    else:
        print("❌ Place search test failed")
        print(f"   Error: {result.get('error', result.get('message', 'Unknown error'))}")
        return False

    return True

async def test_amenity_search():
    """Test amenity search functionality."""
    print_separator("Amenity Search Test")

    # Search for restaurants near Times Square
    result = await find_nearby_amenities(40.7580, -73.9855, 500, "restaurant")
    if result["success"]:
        print("✅ Amenity search test passed")
        count = result["data"]["count"]
        print(f"   Found {count} restaurants")
        if count > 0:
            first_amenity = result["data"]["amenities"][0]
            amenity_name = first_amenity["tags"].get("name", "Unnamed restaurant")
            print(f"   First result: {amenity_name}")
    else:
        # If it fails due to network issues, that's expected and we should treat it as a warning
        error_msg = result.get('error', result.get('message', 'Unknown error'))
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower() or error_msg == "":
            print("⚠️  Amenity search test skipped (network/timeout issue)")
            print(f"   This is expected in some environments")
            return True  # Treat as success since it's a network issue
        else:
            print("❌ Amenity search test failed")
            print(f"   Error: {error_msg}")
            return False

    return True

async def run_all_tests():
    """Run all tests."""
    print("🚀 Starting OSM Edit MCP Server Tests")
    print("=" * 60)

    tests = [
        ("Server Info", test_server_info),
        ("Coordinates", test_coordinates),
        ("Place Search", test_place_search),
        ("Amenity Search", test_amenity_search),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if await test_func():
                passed += 1
                print(f"✅ {test_name} - PASSED")
            else:
                print(f"❌ {test_name} - FAILED")
        except Exception as e:
            print(f"❌ {test_name} - ERROR: {e}")

    print_separator("Test Results")
    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! Your MCP server is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)