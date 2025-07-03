"""
OSM Edit MCP Server

A simple Model Context Protocol server for OpenStreetMap editing operations.
"""

__version__ = "0.1.0"
__author__ = "OSM Edit MCP"

from .server import mcp

__all__ = ["mcp"]