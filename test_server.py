#!/usr/bin/env python3
"""Test script for OSM Edit MCP Server"""

import asyncio
from src.osm_edit_mcp.server import mcp, config

async def test_server():
    """Test server functionality"""
    print("🚀 Testing OSM Edit MCP Server...")
    print(f"✓ Configuration loaded")
    print(f"  - API Base: {config.api_base}")
    print(f"  - Use Dev API: {config.use_dev_api}")
    print(f"  - MCP Server: {config.mcp_server_name} v{config.mcp_server_version}")

    # Test tool loading
    try:
        tools = await mcp.list_tools()
        print(f"✓ {len(tools)} tools loaded successfully:")

        # Group tools by category
        categories = {
            "Basic Operations": [],
            "Natural Language": [],
            "Tag Operations": [],
            "Discovery": [],
            "Validation": [],
            "Other": []
        }

        for tool in tools:
            name = tool.name  # Access as attribute, not dictionary
            if "create_" in name or "query_" in name or "get_user" in name:
                categories["Basic Operations"].append(name)
            elif "parse_natural" in name or "suggest_tags" in name:
                categories["Natural Language"].append(name)
            elif "add_tags" in name or "modify_tags" in name or "remove_tags" in name:
                categories["Tag Operations"].append(name)
            elif "search_" in name or "get_tag_" in name:
                categories["Discovery"].append(name)
            elif "validate_" in name or "explain_" in name:
                categories["Validation"].append(name)
            else:
                categories["Other"].append(name)

        for category, tool_list in categories.items():
            if tool_list:
                print(f"\n  📂 {category}:")
                for tool_name in sorted(tool_list):
                    print(f"    - {tool_name}")

        print(f"\n✅ Server test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error testing server: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_server())
    exit(0 if success else 1)