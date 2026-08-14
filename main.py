#!/usr/bin/env python3
"""
Main entry point for the OSM Edit MCP Server
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from osm_edit_mcp.server import main


if __name__ == "__main__":
    main()
