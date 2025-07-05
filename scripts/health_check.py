#!/usr/bin/env python3
"""
Health check script for OSM Edit MCP Server
Returns exit code 0 if healthy, 1 if not
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.osm_edit_mcp.server import get_server_info, config


async def check_health():
    """Check if the server is healthy."""
    try:
        # Try to get server info
        result = await get_server_info()
        
        if result.get('success'):
            data = result.get('data', {})
            print("✅ Server is healthy")
            print(f"   Version: {data.get('version', 'Unknown')}")
            print(f"   API Mode: {data.get('api_mode', 'Unknown')}")
            print(f"   Authenticated: {data.get('authenticated', False)}")
            return 0
        else:
            print("❌ Server returned error:", result.get('error', 'Unknown error'))
            return 1
            
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return 1


def main():
    """Run health check and exit with appropriate code."""
    exit_code = asyncio.run(check_health())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()