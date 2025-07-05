#!/usr/bin/env python3
"""
Test script to verify server can be imported and initialized
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from osm_edit_mcp.server import mcp, config
    print("✅ Successfully imported OSM Edit MCP Server")
    print(f"   Server name: {mcp.name}")
    print(f"   API Mode: {'Development' if config.osm_use_dev_api else 'Production'}")
    print(f"   API URL: {config.current_api_base_url}")
    print("\n📝 Note: MCP servers communicate via stdin/stdout")
    print("   They are meant to be started by MCP clients like:")
    print("   - Cursor IDE")
    print("   - Claude Desktop")
    print("   - Continue.dev")
    print("   - Cline (VSCode)")
    print("\n💡 To test functionality, use:")
    print("   - python test_comprehensive.py")
    print("   - python quick_test.py")
except Exception as e:
    print(f"❌ Error importing server: {e}")
    import traceback
    traceback.print_exc()