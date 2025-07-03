#!/usr/bin/env python3
"""
Main entry point for the OSM Edit MCP Server
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import mcp

def main():
    """Main entry point"""
    print("Starting OSM Edit MCP Server...")
    mcp.run()

if __name__ == "__main__":
    main()
