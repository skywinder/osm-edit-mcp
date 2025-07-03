"""
OSM Edit MCP Server

A Model Context Protocol server for editing OpenStreetMap data.
"""

__version__ = "0.1.0"
__author__ = "pk"
__email__ = "right.crew7885@fastmail.com"

from .server import main, create_server

__all__ = ["main", "create_server"]