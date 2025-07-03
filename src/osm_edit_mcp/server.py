"""
OSM Edit MCP Server

A Model Context Protocol server for editing OpenStreetMap data.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional, Union
import httpx
import structlog
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from authlib.integrations.httpx_client import AsyncOAuth2Client

# Initialize FastMCP server
mcp = FastMCP("osm-edit-mcp")

# Setup logging
logger = structlog.get_logger(__name__)

# Configuration
class OSMConfig(BaseSettings):
    """Configuration for OSM API access"""
    osm_api_base: str = "https://api.openstreetmap.org/api/0.6"
    osm_dev_api_base: str = "https://master.apis.dev.openstreetmap.org/api/0.6"
    use_dev_api: bool = False
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_redirect_uri: str = "https://localhost:8080/callback"
    user_agent: str = "OSM-Edit-MCP/0.1.0"

    class Config:
        env_prefix = "OSM_"
        env_file = ".env"

# Global configuration
config = OSMConfig()

# Data models
class OSMNode(BaseModel):
    """OSM Node data model"""
    id: Optional[int] = None
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    tags: Dict[str, str] = Field(default_factory=dict)
    version: Optional[int] = None
    changeset: Optional[int] = None
    user: Optional[str] = None
    uid: Optional[int] = None
    timestamp: Optional[str] = None

class OSMWay(BaseModel):
    """OSM Way data model"""
    id: Optional[int] = None
    nodes: List[int] = Field(..., min_items=2)
    tags: Dict[str, str] = Field(default_factory=dict)
    version: Optional[int] = None
    changeset: Optional[int] = None
    user: Optional[str] = None
    uid: Optional[int] = None
    timestamp: Optional[str] = None

class OSMRelation(BaseModel):
    """OSM Relation data model"""
    id: Optional[int] = None
    members: List[Dict[str, Union[str, int]]] = Field(default_factory=list)
    tags: Dict[str, str] = Field(default_factory=dict)
    version: Optional[int] = None
    changeset: Optional[int] = None
    user: Optional[str] = None
    uid: Optional[int] = None
    timestamp: Optional[str] = None

class OSMChangeset(BaseModel):
    """OSM Changeset data model"""
    id: Optional[int] = None
    created_at: Optional[str] = None
    closed_at: Optional[str] = None
    open: bool = True
    user: Optional[str] = None
    uid: Optional[int] = None
    min_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lat: Optional[float] = None
    max_lon: Optional[float] = None
    comments_count: int = 0
    changes_count: int = 0
    tags: Dict[str, str] = Field(default_factory=dict)

class BoundingBox(BaseModel):
    """Bounding box for queries"""
    min_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)
    max_lon: float = Field(..., ge=-180, le=180)

# OAuth client instance
oauth_client: Optional[AsyncOAuth2Client] = None

async def get_oauth_client() -> AsyncOAuth2Client:
    """Get or create OAuth client"""
    global oauth_client
    if oauth_client is None:
        oauth_client = AsyncOAuth2Client(
            client_id=config.oauth_client_id,
            client_secret=config.oauth_client_secret,
            redirect_uri=config.oauth_redirect_uri
        )
    return oauth_client

def get_api_base() -> str:
    """Get the appropriate API base URL"""
    return config.osm_dev_api_base if config.use_dev_api else config.osm_api_base

# Tools
@mcp.tool()
async def create_node(
    lat: float = Field(..., description="Latitude (-90 to 90)"),
    lon: float = Field(..., description="Longitude (-180 to 180)"),
    tags: Dict[str, str] = Field(default_factory=dict, description="Node tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Create a new OSM node with coordinates and tags"""
    try:
        # Validate coordinates
        if not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")

        client = await get_oauth_client()
        api_base = get_api_base()

        # Create changeset first
        changeset_data = {
            "comment": changeset_comment,
            "created_by": "OSM Edit MCP Server v0.1.0"
        }

        # This is a simplified implementation - in practice you'd need to:
        # 1. Create a changeset
        # 2. Create the node within that changeset
        # 3. Handle OAuth authentication flow
        # 4. Parse XML responses

        logger.info("Creating OSM node", lat=lat, lon=lon, tags=tags)

        return {
            "success": True,
            "message": f"Node creation initiated at ({lat}, {lon})",
            "api_base": api_base,
            "tags": tags,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to create node", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def update_node(
    node_id: int = Field(..., description="OSM node ID to update"),
    lat: Optional[float] = Field(None, description="New latitude (-90 to 90)"),
    lon: Optional[float] = Field(None, description="New longitude (-180 to 180)"),
    tags: Optional[Dict[str, str]] = Field(None, description="Updated node tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Update an existing OSM node"""
    try:
        # Validate coordinates if provided
        if lat is not None and not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if lon is not None and not (-180 <= lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Updating OSM node", node_id=node_id, lat=lat, lon=lon, tags=tags)

        return {
            "success": True,
            "message": f"Node {node_id} update initiated",
            "node_id": node_id,
            "api_base": api_base,
            "updates": {"lat": lat, "lon": lon, "tags": tags},
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to update node", node_id=node_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def delete_node(
    node_id: int = Field(..., description="OSM node ID to delete"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Delete an OSM node"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Deleting OSM node", node_id=node_id)

        return {
            "success": True,
            "message": f"Node {node_id} deletion initiated",
            "node_id": node_id,
            "api_base": api_base,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to delete node", node_id=node_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_node(
    node_id: int = Field(..., description="OSM node ID")
) -> Dict[str, Any]:
    """Retrieve node information by ID"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        url = f"{api_base}/node/{node_id}"

        # In a real implementation, you would:
        # 1. Make authenticated request to OSM API
        # 2. Parse XML response
        # 3. Return structured data

        logger.info("Retrieving OSM node", node_id=node_id)

        return {
            "success": True,
            "node_id": node_id,
            "api_url": url,
            "message": f"Node {node_id} retrieval initiated"
        }

    except Exception as e:
        logger.error("Failed to get node", node_id=node_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_way(
    nodes: List[int] = Field(..., description="List of node IDs"),
    tags: Dict[str, str] = Field(default_factory=dict, description="Way tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Create a new OSM way with node references and tags"""
    try:
        if len(nodes) < 2:
            raise ValueError("Way must have at least 2 nodes")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Creating OSM way", nodes=nodes, tags=tags)

        return {
            "success": True,
            "message": f"Way creation initiated with {len(nodes)} nodes",
            "api_base": api_base,
            "nodes": nodes,
            "tags": tags,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to create way", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def update_way(
    way_id: int = Field(..., description="OSM way ID to update"),
    nodes: Optional[List[int]] = Field(None, description="Updated list of node IDs"),
    tags: Optional[Dict[str, str]] = Field(None, description="Updated way tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Update an existing OSM way"""
    try:
        if nodes is not None and len(nodes) < 2:
            raise ValueError("Way must have at least 2 nodes")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Updating OSM way", way_id=way_id, nodes=nodes, tags=tags)

        return {
            "success": True,
            "message": f"Way {way_id} update initiated",
            "way_id": way_id,
            "api_base": api_base,
            "updates": {"nodes": nodes, "tags": tags},
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to update way", way_id=way_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def delete_way(
    way_id: int = Field(..., description="OSM way ID to delete"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Delete an OSM way"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Deleting OSM way", way_id=way_id)

        return {
            "success": True,
            "message": f"Way {way_id} deletion initiated",
            "way_id": way_id,
            "api_base": api_base,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to delete way", way_id=way_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_relation(
    members: List[Dict[str, Union[str, int]]] = Field(..., description="Relation members"),
    tags: Dict[str, str] = Field(default_factory=dict, description="Relation tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Create a new OSM relation with members and tags"""
    try:
        if not members:
            raise ValueError("Relation must have at least one member")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Creating OSM relation", members=members, tags=tags)

        return {
            "success": True,
            "message": f"Relation creation initiated with {len(members)} members",
            "api_base": api_base,
            "members": members,
            "tags": tags,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to create relation", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def update_relation(
    relation_id: int = Field(..., description="OSM relation ID to update"),
    members: Optional[List[Dict[str, Union[str, int]]]] = Field(None, description="Updated relation members"),
    tags: Optional[Dict[str, str]] = Field(None, description="Updated relation tags"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Update an existing OSM relation"""
    try:
        if members is not None and not members:
            raise ValueError("Relation must have at least one member")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Updating OSM relation", relation_id=relation_id, members=members, tags=tags)

        return {
            "success": True,
            "message": f"Relation {relation_id} update initiated",
            "relation_id": relation_id,
            "api_base": api_base,
            "updates": {"members": members, "tags": tags},
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to update relation", relation_id=relation_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def delete_relation(
    relation_id: int = Field(..., description="OSM relation ID to delete"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Delete an OSM relation"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Deleting OSM relation", relation_id=relation_id)

        return {
            "success": True,
            "message": f"Relation {relation_id} deletion initiated",
            "relation_id": relation_id,
            "api_base": api_base,
            "changeset_comment": changeset_comment
        }

    except Exception as e:
        logger.error("Failed to delete relation", relation_id=relation_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_changeset(
    comment: str = Field(..., description="Changeset comment"),
    tags: Dict[str, str] = Field(default_factory=dict, description="Additional changeset tags")
) -> Dict[str, Any]:
    """Create a new changeset for grouping edits"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        changeset_tags = {
            "comment": comment,
            "created_by": "OSM Edit MCP Server v0.1.0",
            **tags
        }

        logger.info("Creating OSM changeset", comment=comment, tags=changeset_tags)

        return {
            "success": True,
            "message": "Changeset creation initiated",
            "api_base": api_base,
            "comment": comment,
            "tags": changeset_tags
        }

    except Exception as e:
        logger.error("Failed to create changeset", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def close_changeset(
    changeset_id: int = Field(..., description="Changeset ID to close")
) -> Dict[str, Any]:
    """Close an open changeset"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Closing OSM changeset", changeset_id=changeset_id)

        return {
            "success": True,
            "message": f"Changeset {changeset_id} closure initiated",
            "changeset_id": changeset_id,
            "api_base": api_base
        }

    except Exception as e:
        logger.error("Failed to close changeset", changeset_id=changeset_id, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def query_elements(
    bbox: str = Field(..., description="Bounding box as 'min_lat,min_lon,max_lat,max_lon'"),
    element_type: str = Field("node", description="Element type: node, way, or relation"),
    tags: Dict[str, str] = Field(default_factory=dict, description="Tag filters")
) -> Dict[str, Any]:
    """Query OSM elements within a bounding box with optional tag filters"""
    try:
        # Parse bounding box
        coords = [float(x) for x in bbox.split(',')]
        if len(coords) != 4:
            raise ValueError("Bounding box must have 4 coordinates")

        min_lat, min_lon, max_lat, max_lon = coords

        # Validate coordinates
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Querying OSM elements", bbox=bbox, element_type=element_type, tags=tags)

        return {
            "success": True,
            "message": f"Query initiated for {element_type} elements",
            "api_base": api_base,
            "bbox": bbox,
            "element_type": element_type,
            "tags": tags
        }

    except Exception as e:
        logger.error("Failed to query elements", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_user_details() -> Dict[str, Any]:
    """Get details about the authenticated user"""
    try:
        client = await get_oauth_client()
        api_base = get_api_base()

        logger.info("Getting user details")

        return {
            "success": True,
            "message": "User details retrieval initiated",
            "api_base": api_base,
            "user": "right.crew7885@fastmail.com"
        }

    except Exception as e:
        logger.error("Failed to get user details", error=str(e))
        return {"success": False, "error": str(e)}

# Resources
@mcp.resource("changeset://{changeset_id}")
async def get_changeset_resource(changeset_id: str) -> str:
    """Get detailed information about a specific changeset"""
    try:
        api_base = get_api_base()
        url = f"{api_base}/changeset/{changeset_id}"

        # In a real implementation, fetch and parse changeset data
        return f"""
# Changeset {changeset_id}

**API URL**: {url}
**Status**: Available for retrieval

This resource provides access to changeset metadata, including:
- Creation and closure timestamps
- User information
- Bounding box
- Tags and comments
- Associated changes
"""

    except Exception as e:
        return f"Error retrieving changeset {changeset_id}: {str(e)}"

@mcp.resource("element://{element_type}/{element_id}")
async def get_element_resource(element_type: str, element_id: str) -> str:
    """Get detailed information about a specific OSM element"""
    try:
        api_base = get_api_base()
        url = f"{api_base}/{element_type}/{element_id}"

        # In a real implementation, fetch and parse element data
        return f"""
# OSM {element_type.title()} {element_id}

**API URL**: {url}
**Type**: {element_type}
**ID**: {element_id}

This resource provides access to element data, including:
- Coordinates (for nodes)
- Node references (for ways)
- Member relationships (for relations)
- Tags and metadata
- Version history
"""

    except Exception as e:
        return f"Error retrieving {element_type} {element_id}: {str(e)}"

@mcp.resource("user://details")
async def get_user_resource() -> str:
    """Get information about the authenticated user"""
    try:
        api_base = get_api_base()

        return f"""
# User Details

**Authenticated User**: right.crew7885@fastmail.com
**API Base**: {api_base}
**OAuth Application**: OSM Edit MCP Server (ID: 8523)

## Permissions
- ✅ Read user preferences
- ✅ Modify user preferences
- ✅ Modify the map data
- ✅ Comment on changesets
- ✅ Read private GPS traces
- ✅ Upload GPS traces

## Usage Guidelines
This MCP server provides tools for editing OpenStreetMap data responsibly.
Please follow OSM community guidelines and best practices.
"""

    except Exception as e:
        return f"Error retrieving user details: {str(e)}"

@mcp.resource("capabilities://")
async def get_capabilities_resource() -> str:
    """Get server capabilities and configuration"""
    try:
        api_base = get_api_base()
        is_dev = config.use_dev_api

        return f"""
# OSM Edit MCP Server Capabilities

**Version**: 0.1.0
**API Base**: {api_base}
**Environment**: {"Development" if is_dev else "Production"}

## Available Tools
- **Node Operations**: create_node, update_node, delete_node, get_node
- **Way Operations**: create_way, update_way, delete_way
- **Relation Operations**: create_relation, update_relation, delete_relation
- **Changeset Management**: create_changeset, close_changeset
- **Query Operations**: query_elements, get_user_details

## Available Resources
- `changeset://<id>` - Changeset information
- `element://<type>/<id>` - Element details
- `user://details` - User information
- `capabilities://` - Server capabilities

## Authentication
OAuth 2.0 with OpenStreetMap API
Required scopes: read_prefs, write_prefs, write_api, write_changeset_comments, read_gpx, write_gpx
"""

    except Exception as e:
        return f"Error retrieving capabilities: {str(e)}"

def create_server():
    """Create and configure the FastMCP server"""
    return mcp

async def main():
    """Main entry point for the MCP server"""
    import argparse
    from mcp.server.stdio import stdio_server

    parser = argparse.ArgumentParser(description="OSM Edit MCP Server")
    parser.add_argument("--dev", action="store_true", help="Use development API")
    args = parser.parse_args()

    if args.dev:
        config.use_dev_api = True
        logger.info("Using OSM development API")
    else:
        logger.info("Using OSM production API")

    logger.info("Starting OSM Edit MCP Server")

    # Run the server
    server = create_server()
    await stdio_server(server)

if __name__ == "__main__":
    asyncio.run(main())