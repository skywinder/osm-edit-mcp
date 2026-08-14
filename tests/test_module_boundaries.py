"""Contracts for the split package architecture."""

import src.osm_edit_mcp.app as app_module
from src.osm_edit_mcp import natural_language, read_tools, server, write_tools


def test_tool_modules_share_one_mcp_application():
    assert server.mcp is app_module.mcp
    assert read_tools.mcp is app_module.mcp
    assert write_tools.mcp is app_module.mcp


def test_server_preserves_read_and_write_tool_imports():
    assert server.get_osm_node is read_tools.get_osm_node
    assert server.search_osm_elements is read_tools.search_osm_elements
    assert server.create_changeset is write_tools.create_changeset
    assert server.create_osm_node is write_tools.create_osm_node


def test_server_preserves_natural_language_imports():
    assert (
        server.parse_natural_language_request
        is natural_language.parse_natural_language_request
    )
    assert server.map_features_to_tags is natural_language.map_features_to_tags
