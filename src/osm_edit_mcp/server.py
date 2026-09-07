"""Compatibility facade and entry point for the OSM Edit MCP server.

The implementation is split by responsibility across focused modules. Public
imports from `osm_edit_mcp.server` remain available for existing MCP clients,
the FastAPI wrapper, scripts, and third-party callers.
"""

import sys

from .app import app, mcp
from .config import USER_AGENT, OSMConfig, config, logger, setup_logging
from .edit_tools import (
    get_edit_capabilities,
    inspect_map_context,
    list_edit_proposals,
    verify_osm_edit,
)
from .http_client import (
    PUBLIC_API_TIMEOUT,
    describe_exception,
    get_authenticated_client,
    get_public_client,
    overpass_literal,
)
from .natural_language import (
    ACTION_MAPPINGS,
    BUSINESS_TYPES,
    FEATURE_MAPPINGS,
    OPENING_HOURS_PATTERNS,
    extract_action_from_text,
    map_business_type_to_tags,
    map_features_to_tags,
    parse_address_components,
    parse_natural_language_request,
    parse_opening_hours,
)
from .prompts import review_gpx_road_edit
from .read_tools import (
    check_authentication,
    export_osm_data,
    find_nearby_amenities,
    get_changeset,
    get_changeset_history,
    get_osm_elements_in_area,
    get_osm_node,
    get_osm_relation,
    get_osm_statistics,
    get_osm_way,
    get_place_info,
    get_server_info,
    parse_natural_language_osm_request,
    search_nearby_places,
    search_osm_elements,
    smart_geocode,
    validate_coordinates,
    validate_osm_data,
)
from .token_store import get_current_user_info, load_oauth_token
from .track_tools import (
    analyze_gpx_track,
    apply_osm_edit,
    apply_track_road_edit,
    create_track_selection,
    match_track_selection,
    preview_track_road_edit,
    suggest_track_road_candidates,
)
from .write_tools import (
    bulk_create_places,
    close_changeset,
    create_changeset,
    create_osm_node,
    create_osm_relation,
    create_osm_way,
    create_place_from_description,
    delete_osm_node,
    delete_osm_relation,
    delete_osm_way,
    delete_place_from_description,
    find_and_update_place,
    update_osm_node,
    update_osm_relation,
    update_osm_way,
)
from .xml_models import build_tags_xml, parse_osm_xml

# Retained for callers that imported the legacy placeholder.
osm_client = None


def main() -> None:
    """Run the FastMCP server using its default stdio transport."""
    setup_logging()
    logger.info("Starting OSM Edit MCP Server...")
    logger.info("Python version: %s", sys.version)
    logger.info("Server version: %s", config.mcp_server_version)
    logger.info(
        "API mode: %s",
        config.api_environment.title(),
    )

    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as exc:
        logger.error("Server error: %s", exc)
        raise SystemExit(1) from exc


__all__ = [
    "ACTION_MAPPINGS",
    "BUSINESS_TYPES",
    "FEATURE_MAPPINGS",
    "OPENING_HOURS_PATTERNS",
    "OSMConfig",
    "PUBLIC_API_TIMEOUT",
    "USER_AGENT",
    "app",
    "analyze_gpx_track",
    "apply_osm_edit",
    "apply_track_road_edit",
    "build_tags_xml",
    "bulk_create_places",
    "check_authentication",
    "close_changeset",
    "config",
    "create_changeset",
    "create_track_selection",
    "create_osm_node",
    "create_osm_relation",
    "create_osm_way",
    "create_place_from_description",
    "delete_osm_node",
    "delete_osm_relation",
    "delete_osm_way",
    "delete_place_from_description",
    "describe_exception",
    "export_osm_data",
    "extract_action_from_text",
    "find_and_update_place",
    "find_nearby_amenities",
    "get_authenticated_client",
    "get_changeset",
    "get_changeset_history",
    "get_current_user_info",
    "get_edit_capabilities",
    "get_osm_elements_in_area",
    "get_osm_node",
    "get_osm_relation",
    "get_osm_statistics",
    "get_osm_way",
    "get_place_info",
    "get_public_client",
    "get_server_info",
    "load_oauth_token",
    "inspect_map_context",
    "list_edit_proposals",
    "logger",
    "main",
    "map_business_type_to_tags",
    "map_features_to_tags",
    "match_track_selection",
    "mcp",
    "osm_client",
    "overpass_literal",
    "parse_address_components",
    "parse_natural_language_osm_request",
    "parse_natural_language_request",
    "parse_opening_hours",
    "parse_osm_xml",
    "preview_track_road_edit",
    "review_gpx_road_edit",
    "search_nearby_places",
    "search_osm_elements",
    "setup_logging",
    "smart_geocode",
    "suggest_track_road_candidates",
    "update_osm_node",
    "update_osm_relation",
    "update_osm_way",
    "validate_coordinates",
    "validate_osm_data",
    "verify_osm_edit",
]


if __name__ == "__main__":
    main()
