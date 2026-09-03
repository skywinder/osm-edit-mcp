"""Shared FastMCP application instance.

Tool modules import this singleton to register their functions without creating
cycles through the compatibility-facing :mod:`osm_edit_mcp.server` module.
"""

from mcp.server.fastmcp import FastMCP

from ._version import __version__

mcp = FastMCP("osm-edit-mcp")
# FastMCP 1.x does not expose the low-level server's version argument. Without
# this assignment, the initialize handshake reports the MCP SDK version rather
# than this distribution's version. The mcp<2 constraint and handshake tests
# make this small compatibility boundary explicit.
mcp._mcp_server.version = __version__
app = mcp


__all__ = ["app", "mcp"]
