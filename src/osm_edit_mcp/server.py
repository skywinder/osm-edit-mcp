"""
OSM Edit MCP Server

A simple Model Context Protocol server for basic OpenStreetMap operations.
Supports reading, fetching, and updating OSM data with changeset management.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional, Union
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from authlib.integrations.httpx_client import AsyncOAuth2Client
import json
from datetime import datetime
import xml.etree.ElementTree as ET

# Initialize FastMCP server
mcp = FastMCP("osm-edit-mcp")

# Configuration
class OSMConfig(BaseSettings):
    """OSM API configuration"""
    osm_api_base_url: str = Field(default="https://api06.dev.openstreetmap.org/api/0.6")
    osm_client_id: str = Field(default="")
    osm_client_secret: str = Field(default="")
    osm_redirect_uri: str = Field(default="http://localhost:8080/callback")
    log_level: str = Field(default="INFO")

    class Config:
        env_file = ".env"

config = OSMConfig()

# Global client instance
osm_client = None

# Helper functions
def parse_osm_xml(xml_content: str) -> Dict[str, Any]:
    """Parse OSM XML response into JSON format."""
    try:
        root = ET.fromstring(xml_content)
        result = {"elements": []}

        for element in root:
            if element.tag in ["node", "way", "relation"]:
                elem_data = {
                    "type": element.tag,
                    "id": int(element.get("id", 0)),
                    "version": int(element.get("version", 0)),
                    "changeset": int(element.get("changeset", 0)),
                    "timestamp": element.get("timestamp", ""),
                    "user": element.get("user", ""),
                    "uid": int(element.get("uid", 0)),
                    "tags": {}
                }

                if element.tag == "node":
                    elem_data["lat"] = float(element.get("lat", 0))
                    elem_data["lon"] = float(element.get("lon", 0))
                elif element.tag == "way":
                    elem_data["nodes"] = []
                    for nd in element.findall("nd"):
                        elem_data["nodes"].append(int(nd.get("ref")))
                elif element.tag == "relation":
                    elem_data["members"] = []
                    for member in element.findall("member"):
                        elem_data["members"].append({
                            "type": member.get("type"),
                            "ref": int(member.get("ref")),
                            "role": member.get("role", "")
                        })

                # Parse tags
                for tag in element.findall("tag"):
                    elem_data["tags"][tag.get("k")] = tag.get("v")

                result["elements"].append(elem_data)

        return result
    except ET.ParseError as e:
        return {"error": f"Failed to parse XML: {str(e)}"}

# MCP Tools
@mcp.tool()
async def get_osm_node(node_id: int) -> Dict[str, Any]:
    """Get an OSM node by ID.

    Args:
        node_id: The ID of the node to retrieve

    Returns:
        Dictionary containing node data including coordinates and tags
    """
    try:
        url = f"{config.osm_api_base_url}/node/{node_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved node {node_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve node {node_id}"
        }

@mcp.tool()
async def get_osm_way(way_id: int) -> Dict[str, Any]:
    """Get an OSM way by ID.

    Args:
        way_id: The ID of the way to retrieve

    Returns:
        Dictionary containing way data including nodes and tags
    """
    try:
        url = f"{config.osm_api_base_url}/way/{way_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved way {way_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve way {way_id}"
        }

@mcp.tool()
async def get_osm_relation(relation_id: int) -> Dict[str, Any]:
    """Get an OSM relation by ID.

    Args:
        relation_id: The ID of the relation to retrieve

    Returns:
        Dictionary containing relation data including members and tags
    """
    try:
        url = f"{config.osm_api_base_url}/relation/{relation_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved relation {relation_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve relation {relation_id}"
        }

@mcp.tool()
async def get_osm_elements_in_area(bbox: str) -> Dict[str, Any]:
    """Get OSM elements within a bounding box.

    Args:
        bbox: Bounding box as "min_lon,min_lat,max_lon,max_lat"

    Returns:
        Dictionary containing all elements in the area
    """
    try:
        url = f"{config.osm_api_base_url}/map?bbox={bbox}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved elements in bounding box {bbox}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve elements in area {bbox}"
        }

@mcp.tool()
async def create_changeset(comment: str, tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Create a new changeset for OSM edits.

    Args:
        comment: Description of the changes being made
        tags: Optional additional tags for the changeset

    Returns:
        Dictionary containing changeset ID and status
    """
    try:
        changeset_tags = {
            "comment": comment,
            "created_by": "OSM Edit MCP Server"
        }
        if tags:
            changeset_tags.update(tags)

        # Create changeset XML
        changeset_xml = "<osm><changeset>"
        for key, value in changeset_tags.items():
            changeset_xml += f'<tag k="{key}" v="{value}"/>'
        changeset_xml += "</changeset></osm>"

        url = f"{config.osm_api_base_url}/changeset/create"
        async with httpx.AsyncClient() as client:
            response = await client.put(
                url,
                content=changeset_xml,
                headers={"Content-Type": "text/xml"}
            )
            response.raise_for_status()
            changeset_id = int(response.text.strip())

            return {
                "success": True,
                "changeset_id": changeset_id,
                "message": f"Created changeset {changeset_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to create changeset"
        }

@mcp.tool()
async def get_changeset(changeset_id: int) -> Dict[str, Any]:
    """Get information about a changeset.

    Args:
        changeset_id: The ID of the changeset to retrieve

    Returns:
        Dictionary containing changeset information
    """
    try:
        url = f"{config.osm_api_base_url}/changeset/{changeset_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved changeset {changeset_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve changeset {changeset_id}"
        }

@mcp.tool()
async def close_changeset(changeset_id: int) -> Dict[str, Any]:
    """Close a changeset.

    Args:
        changeset_id: The ID of the changeset to close

    Returns:
        Dictionary containing operation status
    """
    try:
        url = f"{config.osm_api_base_url}/changeset/{changeset_id}/close"
        async with httpx.AsyncClient() as client:
            response = await client.put(url)
            response.raise_for_status()
            return {
                "success": True,
                "message": f"Closed changeset {changeset_id}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to close changeset {changeset_id}"
        }

@mcp.tool()
async def get_server_info() -> Dict[str, Any]:
    """Get information about the OSM Edit MCP server.

    Returns:
        Dictionary containing server configuration and status
    """
    return {
        "server_name": "OSM Edit MCP Server",
        "version": "1.0.0",
        "api_base_url": config.osm_api_base_url,
        "available_operations": [
            "get_osm_node",
            "get_osm_way",
            "get_osm_relation",
            "get_osm_elements_in_area",
            "create_changeset",
            "get_changeset",
            "close_changeset",
            "get_server_info"
        ],
        "description": "Basic OSM read/fetch/update operations via MCP"
    }
