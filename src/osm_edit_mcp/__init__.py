"""
OSM Edit MCP Server

A simple Model Context Protocol server for OpenStreetMap editing operations.
"""

from ._version import __version__

from .server import mcp

__author__ = "skywinder"

__all__ = ["__version__", "mcp"]
