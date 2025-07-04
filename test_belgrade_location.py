#!/usr/bin/env python3
"""
Belgrade Location Test - Real OSM Functionality Demo
====================================================

Test script to demonstrate real OSM editing functionality at Belgrade location:
Coordinates: 44.80366197537814, 20.486398637294773

This script will:
1. Check authentication
2. Create a test changeset
3. Create a test cafe node
4. Close the changeset
5. Clean up (optional)
"""

import asyncio
import sys
import os
import random
from datetime import datetime

# Add the src directory to the path so we can import the server
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from osm_edit_mcp.server import (
    check_authentication, create_changeset, create_osm_node,
    close_changeset, get_osm_node, config
)

# Belgrade test location
BELGRADE_LAT = 44.80366197537814
BELGRADE_LON = 20.486398637294773

async def main():
    """Test real OSM functionality at Belgrade location"""
    print("🏛️  Belgrade OSM Test - Real Functionality Demo")
    print("=" * 60)
    print(f"📍 Location: {BELGRADE_LAT}, {BELGRADE_LON}")
    print(f"🌐 API Mode: {'Development' if config.osm_use_dev_api else 'Production'}")
    print(f"🔗 API URL: {config.current_api_base_url}")
    print()

    # Step 1: Check Authentication
    print("1️⃣  Checking authentication...")
    auth_result = await check_authentication()
    if auth_result.get('success'):
        username = auth_result.get('data', {}).get('username', 'unknown')
        print(f"   ✅ Authenticated as: {username}")
    else:
        print(f"   ❌ Authentication failed: {auth_result.get('error')}")
        print("   💡 Run 'python oauth_auth.py' to authenticate")
        return
    print()

    # Step 2: Create Test Changeset
    print("2️⃣  Creating test changeset...")
    changeset_comment = f"Belgrade test cafe creation - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    changeset_result = await create_changeset(
        comment=changeset_comment,
        tags={
            "test": "true",
            "location": "Belgrade, Serbia",
            "created_by": "OSM Edit MCP Server - Belgrade Test"
        }
    )

    if changeset_result.get('success'):
        changeset_id = changeset_result.get('data', {}).get('changeset_id')
        print(f"   ✅ Created changeset: {changeset_id}")
    else:
        print(f"   ❌ Failed to create changeset: {changeset_result.get('error')}")
        return
    print()

    # Step 3: Create Test Cafe Node
    print("3️⃣  Creating test cafe at Belgrade location...")
    cafe_name = f"Test Cafe Belgrade {random.randint(1000, 9999)}"
    cafe_tags = {
        "amenity": "cafe",
        "name": cafe_name,
        "opening_hours": "Mo-Su 08:00-22:00",
        "wifi": "yes",
        "outdoor_seating": "yes",
        "note": "Test node created by OSM Edit MCP Server"
    }

    node_result = await create_osm_node(
        lat=BELGRADE_LAT,
        lon=BELGRADE_LON,
        tags=cafe_tags,
        changeset_id=changeset_id
    )

    if node_result.get('success'):
        node_id = node_result.get('data', {}).get('node_id')
        print(f"   ✅ Created cafe node: {node_id}")
        print(f"   📍 Name: {cafe_name}")
        print(f"   📍 Location: {BELGRADE_LAT}, {BELGRADE_LON}")
    else:
        print(f"   ❌ Failed to create node: {node_result.get('error')}")
        node_id = None
    print()

    # Step 4: Close Changeset
    print("4️⃣  Closing changeset...")
    close_result = await close_changeset(changeset_id)
    if close_result.get('success'):
        print(f"   ✅ Closed changeset: {changeset_id}")
    else:
        print(f"   ❌ Failed to close changeset: {close_result.get('error')}")
    print()

    # Step 5: Verify Creation (if node was created)
    if node_id:
        print("5️⃣  Verifying created node...")
        verify_result = await get_osm_node(node_id)
        if verify_result.get('success'):
            node_data = verify_result.get('data', {}).get('elements', [{}])[0]
            print(f"   ✅ Node verified: {node_data.get('id')}")
            print(f"   📍 Tags: {node_data.get('tags', {})}")
        else:
            print(f"   ❌ Failed to verify node: {verify_result.get('error')}")
        print()

    # Summary
    print("📋 Summary:")
    print(f"   • Authentication: {'✅ Working' if auth_result.get('success') else '❌ Failed'}")
    print(f"   • Changeset: {'✅ Created' if changeset_result.get('success') else '❌ Failed'}")
    print(f"   • Node Creation: {'✅ Success' if node_result.get('success') else '❌ Failed'}")
    print(f"   • Changeset Close: {'✅ Closed' if close_result.get('success') else '❌ Failed'}")

    if node_id:
        print()
        print("🎉 SUCCESS! Real OSM node created at Belgrade location!")
        print(f"   View on OSM dev server: https://api06.dev.openstreetmap.org/browse/node/{node_id}")
        print(f"   Changeset: https://api06.dev.openstreetmap.org/browse/changeset/{changeset_id}")
    else:
        print()
        print("⚠️  Node creation failed, but authentication and changeset creation worked!")

if __name__ == "__main__":
    asyncio.run(main())