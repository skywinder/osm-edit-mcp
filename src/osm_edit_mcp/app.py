"""Shared FastMCP application instance.

Tool modules import this singleton to register their functions without creating
cycles through the compatibility-facing :mod:`osm_edit_mcp.server` module.
"""

from typing import Any, Callable, TypeVar, cast

from mcp.server.fastmcp import FastMCP

from ._version import __version__
from .config import config

TAGGING_GUIDANCE = """When preparing OSM edits, prefer established, specific tags for
verifiable facts over prose. For a place known to offer juice, use
drink:juice=yes; this says juice is available, not that it is freshly squeezed
or which fruit it contains. Do not invent unsupported details. cuisine=juice
can describe a juice-focused cuisine, but availability alone does not establish
that classification. Inspect existing tags and preserve unrelated tags and
existing semicolon-separated cuisine values when adding a supported value.
Use description only for concise, neutral, non-redundant information that
cannot be expressed by suitable tags; never use it for advertising or praise.
Check applicable OSM tagging guidance and ask when evidence or tagging is
unclear. Review the exact proposed changes and their source before publication."""

mcp = FastMCP(
    "osm-edit-mcp",
    instructions=TAGGING_GUIDANCE if config.osm_tool_profile == "full" else None,
)
# FastMCP 1.x does not expose the low-level server's version argument. Without
# this assignment, the initialize handshake reports the MCP SDK version rather
# than this distribution's version. The mcp<2 constraint and handshake tests
# make this small compatibility boundary explicit.
mcp._mcp_server.version = __version__
app = mcp

DISCOVERY_TOOLS = {"resolve_location", "search_nearby_places", "get_place_details"}
Function = TypeVar("Function", bound=Callable[..., Any])


def profile_tool(**options: Any) -> Callable[[Function], Function]:
    """Select capabilities at registration, independently of the MCP client."""

    def register(function: Function) -> Function:
        name = options.get("name", function.__name__)
        if config.osm_tool_profile == "full" or name in DISCOVERY_TOOLS:
            mcp.tool(**options)(function)
        return function

    return register


def profile_resource(uri: str, **options: Any) -> Callable[[Function], Function]:
    if config.osm_tool_profile == "full":
        return cast(Callable[[Function], Function], mcp.resource(uri, **options))
    return lambda function: function


def profile_prompt(**options: Any) -> Callable[[Function], Function]:
    if config.osm_tool_profile == "full":
        return cast(Callable[[Function], Function], mcp.prompt(**options))
    return lambda function: function


__all__ = ["app", "mcp"]
