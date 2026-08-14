"""Shared FastMCP application instance.

Tool modules import this singleton to register their functions without creating
cycles through the compatibility-facing :mod:`osm_edit_mcp.server` module.
"""

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("osm-edit-mcp")
app = mcp


__all__ = ["app", "mcp"]
