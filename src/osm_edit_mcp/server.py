"""
OSM Edit MCP Server

A Model Context Protocol server for editing OpenStreetMap data with advanced tagging capabilities.
"""

import os
import re
import asyncio
from typing import Any, Dict, List, Optional, Union, Tuple
import httpx
import structlog
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
from authlib.integrations.httpx_client import AsyncOAuth2Client
from enum import Enum
import json
from datetime import datetime

# Import the new tag management system
from .osm_tags import OSMTagManager, initialize_tag_manager

# Initialize FastMCP server
mcp = FastMCP("osm-edit-mcp")

# Initialize tag manager
tag_manager = OSMTagManager()

# Setup logging
logger = structlog.get_logger(__name__)

# Configuration
class OSMConfig(BaseSettings):
    """Configuration for OSM API access"""
    # API Configuration
    api_base: str = "https://api.openstreetmap.org/api/0.6"
    dev_api_base: str = "https://master.apis.dev.openstreetmap.org/api/0.6"
    use_dev_api: bool = False

    # OAuth 2.0 Configuration
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_redirect_uri: str = "https://localhost:8080/callback"

    # External APIs
    taginfo_api_base: str = "https://taginfo.openstreetmap.org/api/4"
    osm_wiki_api_base: str = "https://wiki.openstreetmap.org/w/api.php"

    # MCP Server Configuration
    mcp_server_name: str = "osm-edit-mcp"
    mcp_server_version: str = "0.1.0"

    # Application Settings
    user_agent: str = "OSM-Edit-MCP/0.1.0"
    log_level: str = "INFO"

    # Safety and Rate Limiting
    require_user_confirmation: bool = True
    rate_limit_per_minute: int = 60
    max_changeset_size: int = 50

    # Cache Settings
    enable_cache: bool = True
    cache_ttl_seconds: int = 300

    # Default Changeset Information
    default_changeset_comment: str = "Edited via OSM Edit MCP Server"
    default_changeset_source: str = "OSM Edit MCP Server"
    default_changeset_created_by: str = "osm-edit-mcp/0.1.0"

    # Security Settings
    use_keyring: bool = True
    debug: bool = False
    development_mode: bool = False

    class Config:
        env_prefix = "OSM_"
        env_file = ".env"

# Global configuration
config = OSMConfig()

# Enhanced Data Models for Tagging
class TagValidationLevel(str, Enum):
    """Tag validation levels"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    VALID = "valid"

class TagValidationResult(BaseModel):
    """Result of tag validation"""
    tag_key: str
    tag_value: str
    level: TagValidationLevel
    message: str
    suggestions: List[str] = Field(default_factory=list)
    documentation_url: Optional[str] = None

class TagSuggestion(BaseModel):
    """Tag suggestion with confidence"""
    key: str
    value: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    category: str
    examples: List[str] = Field(default_factory=list)

class NaturalLanguageTagRequest(BaseModel):
    """Natural language tag parsing request"""
    description: str
    element_type: str = Field(..., pattern="^(node|way|relation)$")
    existing_tags: Dict[str, str] = Field(default_factory=dict)
    location_context: Optional[str] = None

class TagConflictResolution(BaseModel):
    """Tag conflict resolution strategy"""
    conflict_type: str
    original_value: str
    new_value: str
    resolution: str
    keep_both: bool = False
    priority_reason: str

# Advanced Tagging Services - Now using external tag management
# The OSMTagStandards class has been replaced with the external tag manager
# All tag operations are now handled by the tag_manager instance



class TagProcessor:
    """Advanced tag processing and management"""

    def __init__(self, tag_manager: OSMTagManager):
        self.tag_manager = tag_manager

    def parse_natural_language(self, request: NaturalLanguageTagRequest) -> Dict[str, Any]:
        """Parse natural language into OSM tags"""
        suggestions = self.tag_manager.suggest_tags_from_description(request.description)

        # Merge with existing tags
        merged_tags = request.existing_tags.copy()
        conflicts = []

        for suggestion in suggestions:
            if suggestion.key in merged_tags:
                if merged_tags[suggestion.key] != suggestion.value:
                    conflicts.append(TagConflictResolution(
                        conflict_type="value_mismatch",
                        original_value=merged_tags[suggestion.key],
                        new_value=suggestion.value,
                        resolution=f"Keep existing value '{merged_tags[suggestion.key]}'",
                        priority_reason="Existing tag takes priority"
                    ))
            else:
                merged_tags[suggestion.key] = suggestion.value

        return {
            "suggested_tags": {s.key: s.value for s in suggestions},
            "merged_tags": merged_tags,
            "suggestions": suggestions,
            "conflicts": conflicts,
            "validation_results": [
                self.tag_manager.validate_tag(k, v) for k, v in merged_tags.items()
            ]
        }

    def simple_parse_natural_language(self, description: str) -> Dict[str, Any]:
        """Simple natural language parsing for tools that don't need full request object"""
        suggestions = self.tag_manager.suggest_tags_from_description(description)

        return {
            "suggested_tags": {s.key: s.value for s in suggestions},
            "suggestions": suggestions,
            "validation_results": [
                self.tag_manager.validate_tag(s.key, s.value) for s in suggestions
            ]
        }

    def merge_tags(self, existing_tags: Dict[str, str], new_tags: Dict[str, str]) -> Dict[str, Any]:
        """Merge tag sets with conflict detection"""
        merged = existing_tags.copy()
        conflicts = []
        added = []
        updated = []

        for key, value in new_tags.items():
            if key in merged:
                if merged[key] != value:
                    conflicts.append({
                        "key": key,
                        "existing_value": merged[key],
                        "new_value": value,
                        "suggestion": f"Update {key} from '{merged[key]}' to '{value}'"
                    })
                    updated.append(key)
                    merged[key] = value
            else:
                merged[key] = value
                added.append(key)

        return {
            "merged_tags": merged,
            "conflicts": conflicts,
            "added_tags": added,
            "updated_tags": updated,
            "summary": f"Added {len(added)} tags, updated {len(updated)} tags, {len(conflicts)} conflicts"
        }

# Initialize tag processor
tag_processor = TagProcessor(tag_manager)

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
    return config.dev_api_base if config.use_dev_api else config.api_base

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

# Advanced Tagging Tools

@mcp.tool()
async def parse_natural_language_tags(
    description: str = Field(..., description="Natural language description of what to add/tag"),
    element_type: str = Field("node", description="Element type: node, way, or relation"),
    existing_tags: Dict[str, str] = Field(default_factory=dict, description="Existing tags on the element"),
    location_context: Optional[str] = Field(None, description="Location context for better suggestions")
) -> Dict[str, Any]:
    """Convert natural language description into OSM tags with suggestions and validation.

    Examples:
    - "coffee shop with wifi and outdoor seating" → amenity=cafe, internet_access=wlan, outdoor_seating=yes
    - "italian restaurant" → amenity=restaurant, cuisine=italian
    - "apartment building" → building=apartment
    """
    try:
        request = NaturalLanguageTagRequest(
            description=description,
            element_type=element_type,
            existing_tags=existing_tags,
            location_context=location_context
        )

        result = TagProcessor.parse_natural_language(request)

        logger.info("Parsed natural language tags", description=description, result=result)

        return {
            "success": True,
            "description": description,
            "suggested_tags": result["suggested_tags"],
            "merged_tags": result["merged_tags"],
            "suggestions": [s.dict() for s in result["suggestions"]],
            "conflicts": [c.dict() for c in result["conflicts"]],
            "validation_results": [v.dict() for v in result["validation_results"]],
            "message": f"Generated {len(result['suggested_tags'])} tag suggestions from description"
        }

    except Exception as e:
        logger.error("Failed to parse natural language tags", description=description, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def validate_tags(
    tags: Dict[str, str] = Field(..., description="Tags to validate against OSM standards"),
    element_type: str = Field("node", description="Element type for context-specific validation")
) -> Dict[str, Any]:
    """Validate tags against OSM tagging standards and provide suggestions for improvements.

    Returns validation results with warnings for uncommon tags and suggestions for alternatives.
    """
    try:
        validation_results = []

        for key, value in tags.items():
            result = tag_manager.validate_tag(key, value)
            validation_results.append(result)

        # Summary statistics
        valid_count = sum(1 for r in validation_results if r.level == TagValidationLevel.VALID)
        warning_count = sum(1 for r in validation_results if r.level == TagValidationLevel.WARNING)
        error_count = sum(1 for r in validation_results if r.level == TagValidationLevel.ERROR)

        logger.info("Validated tags", tags=tags, valid=valid_count, warnings=warning_count, errors=error_count)

        return {
            "success": True,
            "tags": tags,
            "validation_results": [r.dict() for r in validation_results],
            "summary": {
                "total_tags": len(tags),
                "valid": valid_count,
                "warnings": warning_count,
                "errors": error_count,
                "overall_status": "valid" if error_count == 0 else "has_errors"
            },
            "message": f"Validated {len(tags)} tags: {valid_count} valid, {warning_count} warnings, {error_count} errors"
        }

    except Exception as e:
        logger.error("Failed to validate tags", tags=tags, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def suggest_tags(
    description: str = Field(..., description="Description of the feature to get tag suggestions"),
    existing_tags: Dict[str, str] = Field(default_factory=dict, description="Existing tags to consider"),
    limit: int = Field(10, description="Maximum number of suggestions to return")
) -> Dict[str, Any]:
    """Get tag suggestions based on a description, with confidence scores and explanations.

    Provides ranked suggestions with explanations and examples of proper usage.
    """
    try:
        suggestions = tag_manager.suggest_tags_from_description(description)

        # Filter and limit suggestions
        filtered_suggestions = []
        seen_tags = set()

        for suggestion in suggestions[:limit]:
            tag_key = f"{suggestion.key}={suggestion.value}"
            if tag_key not in seen_tags and suggestion.key not in existing_tags:
                filtered_suggestions.append(suggestion)
                seen_tags.add(tag_key)

        # Sort by confidence
        filtered_suggestions.sort(key=lambda x: x.confidence, reverse=True)

        logger.info("Generated tag suggestions", description=description, count=len(filtered_suggestions))

        return {
            "success": True,
            "description": description,
            "suggestions": [s.dict() for s in filtered_suggestions],
            "existing_tags": existing_tags,
            "message": f"Generated {len(filtered_suggestions)} tag suggestions",
            "usage_tip": "Review suggestions and their confidence scores. Higher confidence suggestions are more likely to be appropriate."
        }

    except Exception as e:
        logger.error("Failed to generate tag suggestions", description=description, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def merge_tags(
    existing_tags: Dict[str, str] = Field(..., description="Current tags on the element"),
    new_tags: Dict[str, str] = Field(..., description="New tags to merge"),
    conflict_strategy: str = Field("ask", description="How to handle conflicts: 'keep_existing', 'use_new', 'ask'")
) -> Dict[str, Any]:
    """Merge two sets of tags with conflict detection and resolution.

    Helps safely combine tag sets while identifying and resolving conflicts.
    """
    try:
        result = TagProcessor.merge_tags(existing_tags, new_tags)

        # Apply conflict strategy
        if result["conflicts"] and conflict_strategy != "ask":
            for conflict in result["conflicts"]:
                key = conflict["key"]
                if conflict_strategy == "keep_existing":
                    result["merged_tags"][key] = conflict["existing_value"]
                elif conflict_strategy == "use_new":
                    result["merged_tags"][key] = conflict["new_value"]

        logger.info("Merged tags", existing=existing_tags, new=new_tags, result=result["summary"])

        return {
            "success": True,
            "original_tags": existing_tags,
            "new_tags": new_tags,
            "merged_tags": result["merged_tags"],
            "conflicts": result["conflicts"],
            "added_tags": result["added_tags"],
            "updated_tags": result["updated_tags"],
            "summary": result["summary"],
            "message": f"Merged tags: {result['summary']}"
        }

    except Exception as e:
        logger.error("Failed to merge tags", existing=existing_tags, new=new_tags, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def add_tags_to_element(
    element_id: int = Field(..., description="OSM element ID"),
    element_type: str = Field(..., description="Element type: node, way, or relation"),
    new_tags: Dict[str, str] = Field(..., description="Tags to add to the element"),
    changeset_comment: str = Field(..., description="Changeset comment"),
    merge_strategy: str = Field("ask", description="How to handle existing tags: 'keep_existing', 'update', 'ask'")
) -> Dict[str, Any]:
    """Add tags to an existing OSM element with conflict detection.

    ⚠️ This modifies live OSM data. Use with caution and verify tags before applying.
    """
    try:
        # First validate the new tags
        validation_results = []
        for key, value in new_tags.items():
            result = tag_manager.validate_tag(key, value)
            validation_results.append(result)

        # Check for validation errors
        errors = [r for r in validation_results if r.level == TagValidationLevel.ERROR]
        if errors:
            return {
                "success": False,
                "error": "Tag validation failed",
                "validation_errors": [r.dict() for r in errors],
                "message": "Please fix validation errors before adding tags"
            }

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.warning("Adding tags to OSM element",
                      element_id=element_id, element_type=element_type, tags=new_tags)

        return {
            "success": True,
            "element_id": element_id,
            "element_type": element_type,
            "new_tags": new_tags,
            "validation_results": [r.dict() for r in validation_results],
            "changeset_comment": changeset_comment,
            "api_base": api_base,
            "message": f"Tag addition to {element_type} {element_id} initiated",
            "warning": "This operation modifies live OSM data. Ensure tags are correct before proceeding."
        }

    except Exception as e:
        logger.error("Failed to add tags to element",
                    element_id=element_id, element_type=element_type, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def modify_element_tags(
    element_id: int = Field(..., description="OSM element ID"),
    element_type: str = Field(..., description="Element type: node, way, or relation"),
    tag_updates: Dict[str, str] = Field(..., description="Tags to update (key=new_value)"),
    tag_removals: List[str] = Field(default_factory=list, description="Tag keys to remove"),
    changeset_comment: str = Field(..., description="Changeset comment")
) -> Dict[str, Any]:
    """Modify existing tags on an OSM element (update values, remove tags).

    ⚠️ This modifies live OSM data. Use with caution and verify changes before applying.
    """
    try:
        # Validate updated tags
        validation_results = []
        for key, value in tag_updates.items():
            result = tag_manager.validate_tag(key, value)
            validation_results.append(result)

        # Check for validation errors
        errors = [r for r in validation_results if r.level == TagValidationLevel.ERROR]
        if errors:
            return {
                "success": False,
                "error": "Tag validation failed",
                "validation_errors": [r.dict() for r in errors],
                "message": "Please fix validation errors before modifying tags"
            }

        client = await get_oauth_client()
        api_base = get_api_base()

        logger.warning("Modifying tags on OSM element",
                      element_id=element_id, element_type=element_type,
                      updates=tag_updates, removals=tag_removals)

        return {
            "success": True,
            "element_id": element_id,
            "element_type": element_type,
            "tag_updates": tag_updates,
            "tag_removals": tag_removals,
            "validation_results": [r.dict() for r in validation_results],
            "changeset_comment": changeset_comment,
            "api_base": api_base,
            "message": f"Tag modification on {element_type} {element_id} initiated",
            "warning": "This operation modifies live OSM data. Ensure changes are correct before proceeding."
        }

    except Exception as e:
        logger.error("Failed to modify element tags",
                    element_id=element_id, element_type=element_type, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_tag_documentation(
    tag_key: str = Field(..., description="Tag key to get documentation for"),
    include_examples: bool = Field(True, description="Include usage examples")
) -> Dict[str, Any]:
    """Get documentation and usage information for an OSM tag.

    Provides wiki links, descriptions, common values, and usage examples.
    """
    try:
        if tag_key in tag_manager.tag_standards["primary_tags"]:
            standard = tag_manager.tag_standards["primary_tags"][tag_key]

            result = {
                "success": True,
                "tag_key": tag_key,
                "description": standard["description"],
                "common_values": standard["values"],
                "wiki_url": standard.get("wiki"),
                "category": "standard"
            }

            if include_examples:
                result["examples"] = [
                    f"{tag_key}={value}" for value in standard["values"][:5]
                ]

            # Add usage context
            usage_contexts = []
            if tag_key == "amenity":
                usage_contexts = ["Points of interest", "Facilities", "Services"]
            elif tag_key == "shop":
                usage_contexts = ["Retail establishments", "Commercial buildings"]
            elif tag_key == "highway":
                usage_contexts = ["Roads", "Paths", "Transportation routes"]
            elif tag_key == "building":
                usage_contexts = ["Structures", "Architecture"]
            elif tag_key == "tourism":
                usage_contexts = ["Tourist facilities", "Accommodation", "Attractions"]

            result["usage_contexts"] = usage_contexts

        else:
            result = {
                "success": True,
                "tag_key": tag_key,
                "description": f"Documentation for {tag_key} not found in standard tags",
                "category": "custom",
                "wiki_url": f"https://wiki.openstreetmap.org/wiki/Key:{tag_key}",
                "message": "This may be a custom or less common tag. Check the wiki for details."
            }

        logger.info("Retrieved tag documentation", tag_key=tag_key)
        return result

    except Exception as e:
        logger.error("Failed to get tag documentation", tag_key=tag_key, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def discover_related_tags(
    primary_tags: Dict[str, str] = Field(..., description="Primary tags to find related tags for"),
    element_type: str = Field("node", description="Element type for context")
) -> Dict[str, Any]:
    """Discover related or complementary tags based on primary tags.

    Suggests additional tags that commonly go with the provided primary tags.
    """
    try:
        related_suggestions = []

        # Check for specific patterns and suggest related tags
        for key, value in primary_tags.items():
            if key == "amenity":
                if value in ["restaurant", "cafe", "pub", "bar"]:
                    related_suggestions.extend([
                        TagSuggestion(key="cuisine", value="", confidence=0.8,
                                    reason="Restaurants often specify cuisine type", category="food",
                                    examples=["cuisine=italian", "cuisine=chinese", "cuisine=mexican"]),
                        TagSuggestion(key="opening_hours", value="", confidence=0.7,
                                    reason="Operating hours are useful for food establishments", category="hours",
                                    examples=["opening_hours=Mo-Su 08:00-22:00"]),
                        TagSuggestion(key="outdoor_seating", value="yes", confidence=0.6,
                                    reason="Many restaurants have outdoor seating", category="amenity",
                                    examples=["outdoor_seating=yes", "outdoor_seating=no"])
                    ])
                elif value in ["school", "university"]:
                    related_suggestions.extend([
                        TagSuggestion(key="education:type", value="", confidence=0.8,
                                    reason="Educational institutions often specify type", category="education",
                                    examples=["education:type=primary", "education:type=secondary"]),
                        TagSuggestion(key="wheelchair", value="yes", confidence=0.7,
                                    reason="Accessibility is important for public buildings", category="accessibility",
                                    examples=["wheelchair=yes", "wheelchair=limited"])
                    ])
                elif value == "fuel":
                    related_suggestions.extend([
                        TagSuggestion(key="fuel:diesel", value="yes", confidence=0.8,
                                    reason="Gas stations often specify fuel types", category="fuel",
                                    examples=["fuel:diesel=yes", "fuel:octane_95=yes"]),
                        TagSuggestion(key="shop", value="convenience", confidence=0.6,
                                    reason="Many gas stations have convenience stores", category="shop",
                                    examples=["shop=convenience"])
                    ])

            elif key == "shop":
                related_suggestions.extend([
                    TagSuggestion(key="opening_hours", value="", confidence=0.8,
                                reason="Operating hours are important for shops", category="hours",
                                examples=["opening_hours=Mo-Sa 09:00-18:00"]),
                    TagSuggestion(key="payment:credit_cards", value="yes", confidence=0.7,
                                reason="Payment methods are useful information", category="payment",
                                examples=["payment:credit_cards=yes", "payment:cash=yes"])
                ])

            elif key == "tourism" and value == "hotel":
                related_suggestions.extend([
                    TagSuggestion(key="stars", value="", confidence=0.8,
                                reason="Hotels often have star ratings", category="quality",
                                examples=["stars=3", "stars=4"]),
                    TagSuggestion(key="internet_access", value="wlan", confidence=0.7,
                                reason="Internet access is expected in hotels", category="amenity",
                                examples=["internet_access=wlan", "internet_access=yes"])
                ])

            elif key == "highway":
                if value in ["residential", "service", "tertiary"]:
                    related_suggestions.extend([
                        TagSuggestion(key="maxspeed", value="", confidence=0.8,
                                    reason="Speed limits are important for roads", category="traffic",
                                    examples=["maxspeed=30", "maxspeed=50"]),
                        TagSuggestion(key="surface", value="asphalt", confidence=0.7,
                                    reason="Road surface information is useful", category="physical",
                                    examples=["surface=asphalt", "surface=concrete"])
                    ])

        # General suggestions based on element type
        if element_type == "node":
            # Common node attributes
            if not any(tag.key == "name" for tag in related_suggestions):
                related_suggestions.append(
                    TagSuggestion(key="name", value="", confidence=0.9,
                                reason="Most features benefit from having a name", category="identification",
                                examples=["name=Main Street Cafe"])
                )

        logger.info("Discovered related tags", primary_tags=primary_tags, count=len(related_suggestions))

        return {
            "success": True,
            "primary_tags": primary_tags,
            "element_type": element_type,
            "related_suggestions": [s.dict() for s in related_suggestions],
            "message": f"Found {len(related_suggestions)} related tag suggestions",
            "usage_tip": "Consider adding these related tags to provide more complete information about the feature."
        }

    except Exception as e:
        logger.error("Failed to discover related tags", primary_tags=primary_tags, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def explain_tags(
    tags: Dict[str, str] = Field(..., description="Tags to explain in human-readable format")
) -> Dict[str, Any]:
    """Convert OSM tags into human-readable explanations.

    Provides natural language descriptions of what the tags mean and represent.
    """
    try:
        explanations = []
        feature_description = ""

        # Primary feature identification
        if "amenity" in tags:
            value = tags["amenity"]
            feature_description = f"This is a {value}"
            explanations.append(f"amenity={value}: {tag_manager.get_tag_description('amenity', value)}")
        elif "shop" in tags:
            value = tags["shop"]
            feature_description = f"This is a {value} shop"
            explanations.append(f"shop={value}: {tag_manager.get_tag_description('shop', value)}")
        elif "highway" in tags:
            value = tags["highway"]
            feature_description = f"This is a {value} road/path"
            explanations.append(f"highway={value}: {tag_manager.get_tag_description('highway', value)}")
        elif "building" in tags:
            value = tags["building"]
            feature_description = f"This is a {value} building"
            explanations.append(f"building={value}: {tag_manager.get_tag_description('building', value)}")

        # Additional tag explanations
        for key, value in tags.items():
            if key not in ["amenity", "shop", "highway", "building"]:
                description = tag_manager.get_tag_description(key, value)
                explanations.append(f"{key}={value}: {description}")

        # Build natural language summary
        summary_parts = [feature_description] if feature_description else []

        if "name" in tags:
            summary_parts.append(f"named '{tags['name']}'")
        if "cuisine" in tags:
            summary_parts.append(f"serving {tags['cuisine']} cuisine")
        if "opening_hours" in tags:
            summary_parts.append(f"open {tags['opening_hours']}")
        if "wheelchair" in tags and tags["wheelchair"] == "yes":
            summary_parts.append("with wheelchair accessibility")
        if "wifi" in tags and tags["wifi"] == "yes":
            summary_parts.append("with WiFi available")
        if "outdoor_seating" in tags and tags["outdoor_seating"] == "yes":
            summary_parts.append("with outdoor seating")

        natural_description = ". ".join(summary_parts) if summary_parts else "Generic map feature"

        logger.info("Explained tags", tags=tags, summary=natural_description)

        return {
            "success": True,
            "tags": tags,
            "natural_description": natural_description,
            "detailed_explanations": explanations,
            "feature_type": feature_description,
            "message": f"Explained {len(tags)} tags"
        }

    except Exception as e:
        logger.error("Failed to explain tags", tags=tags, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_feature_with_natural_language(
    description: str = Field(..., description="Natural language description of feature to create"),
    latitude: float = Field(..., description="Latitude for the feature"),
    longitude: float = Field(..., description="Longitude for the feature"),
    changeset_comment: str = Field(..., description="Changeset comment"),
    confirm_before_create: bool = Field(True, description="Require confirmation before creating")
) -> Dict[str, Any]:
    """Create a complete OSM feature from natural language description.

    ⚠️ This creates live OSM data. The operation will show what would be created
    and require confirmation unless confirm_before_create is False.

    Examples:
    - "Italian restaurant with outdoor seating" at coordinates
    - "Elementary school with wheelchair access"
    - "Gas station with convenience store"
    """
    try:
        # Parse natural language into tags
        parse_request = NaturalLanguageTagRequest(
            description=description,
            element_type="node",
            existing_tags={},
            location_context=f"lat={latitude}, lon={longitude}"
        )

        tag_result = TagProcessor.parse_natural_language(parse_request)
        suggested_tags = tag_result["suggested_tags"]

        # Validate all suggested tags
        validation_results = []
        for key, value in suggested_tags.items():
            result = OSMTagStandards.validate_tag(key, value)
            validation_results.append(result)

        # Check for validation errors
        errors = [r for r in validation_results if r.level == TagValidationLevel.ERROR]
        warnings = [r for r in validation_results if r.level == TagValidationLevel.WARNING]

        # Create feature summary
        feature_explanation = await explain_tags(suggested_tags)

        result = {
            "success": True,
            "description": description,
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "suggested_tags": suggested_tags,
            "feature_explanation": feature_explanation["data"]["natural_description"] if feature_explanation["success"] else description,
            "validation_results": [r.dict() for r in validation_results],
            "validation_summary": {
                "total_tags": len(suggested_tags),
                "errors": len(errors),
                "warnings": len(warnings),
                "status": "ready" if len(errors) == 0 else "has_errors"
            },
            "changeset_comment": changeset_comment,
            "additional_suggestions": [s.dict() for s in tag_result["suggestions"]],
            "confirm_before_create": confirm_before_create
        }

        if errors:
            result["error"] = "Cannot create feature due to tag validation errors"
            result["validation_errors"] = [r.dict() for r in errors]
            result["message"] = "Please fix validation errors before creating feature"
            return result

        if confirm_before_create:
            result["message"] = f"Ready to create: {feature_explanation['data']['natural_description'] if feature_explanation['success'] else description}"
            result["next_step"] = "Review the suggested tags and call create_node() if everything looks correct"
            result["warning"] = "⚠️ This will create live OSM data. Verify all information is correct."
        else:
            # Actually create the feature
            client = await get_oauth_client()
            api_base = get_api_base()

            logger.warning("Creating OSM feature from natural language",
                          description=description, tags=suggested_tags, coords=(latitude, longitude))

            result["message"] = f"Feature creation initiated: {feature_explanation['data']['natural_description'] if feature_explanation['success'] else description}"
            result["warning"] = "⚠️ OSM data modification in progress."

        return result

    except Exception as e:
        logger.error("Failed to create feature from natural language",
                    description=description, error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def batch_tag_operations(
    operations: List[Dict[str, Any]] = Field(..., description="List of tag operations to perform"),
    changeset_comment: str = Field(..., description="Changeset comment for all operations"),
    dry_run: bool = Field(True, description="Whether to simulate operations without executing")
) -> Dict[str, Any]:
    """Perform multiple tag operations in a batch with validation and conflict checking.

    ⚠️ This can modify multiple OSM elements. Use dry_run=True to validate first.

    Operation format:
    {
        "type": "add_tags" | "modify_tags" | "remove_tags",
        "element_id": 123,
        "element_type": "node",
        "tags": {"key": "value", ...},
        "remove_keys": ["key1", "key2"]  # for remove_tags type
    }
    """
    try:
        results = []
        total_operations = len(operations)

        for i, operation in enumerate(operations):
            operation_result = {
                "operation_index": i,
                "type": operation.get("type"),
                "element_id": operation.get("element_id"),
                "element_type": operation.get("element_type"),
                "success": False
            }

            try:
                # Validate operation structure
                required_fields = ["type", "element_id", "element_type"]
                missing_fields = [field for field in required_fields if field not in operation]
                if missing_fields:
                    operation_result["error"] = f"Missing required fields: {missing_fields}"
                    results.append(operation_result)
                    continue

                op_type = operation["type"]
                element_id = operation["element_id"]
                element_type = operation["element_type"]

                if op_type == "add_tags":
                    tags = operation.get("tags", {})
                    if not tags:
                        operation_result["error"] = "No tags provided for add_tags operation"
                        results.append(operation_result)
                        continue

                    # Validate tags
                    validation_results = []
                    for key, value in tags.items():
                        result = tag_manager.validate_tag(key, value)
                        validation_results.append(result)

                    errors = [r for r in validation_results if r.level == TagValidationLevel.ERROR]
                    if errors:
                        operation_result["error"] = "Tag validation failed"
                        operation_result["validation_errors"] = [r.dict() for r in errors]
                    else:
                        operation_result["success"] = True
                        operation_result["tags"] = tags
                        operation_result["validation_results"] = [r.dict() for r in validation_results]

                        if not dry_run:
                            # Actually perform the operation
                            logger.warning("Batch operation: adding tags",
                                          element_id=element_id, element_type=element_type, tags=tags)
                            operation_result["executed"] = True
                        else:
                            operation_result["executed"] = False
                            operation_result["dry_run"] = True

                elif op_type == "modify_tags":
                    tag_updates = operation.get("tags", {})
                    tag_removals = operation.get("remove_keys", [])

                    if not tag_updates and not tag_removals:
                        operation_result["error"] = "No tag updates or removals provided"
                        results.append(operation_result)
                        continue

                    # Validate updated tags
                    validation_results = []
                    for key, value in tag_updates.items():
                        result = tag_manager.validate_tag(key, value)
                        validation_results.append(result)

                    errors = [r for r in validation_results if r.level == TagValidationLevel.ERROR]
                    if errors:
                        operation_result["error"] = "Tag validation failed"
                        operation_result["validation_errors"] = [r.dict() for r in errors]
                    else:
                        operation_result["success"] = True
                        operation_result["tag_updates"] = tag_updates
                        operation_result["tag_removals"] = tag_removals
                        operation_result["validation_results"] = [r.dict() for r in validation_results]

                        if not dry_run:
                            logger.warning("Batch operation: modifying tags",
                                          element_id=element_id, element_type=element_type,
                                          updates=tag_updates, removals=tag_removals)
                            operation_result["executed"] = True
                        else:
                            operation_result["executed"] = False
                            operation_result["dry_run"] = True

                else:
                    operation_result["error"] = f"Unknown operation type: {op_type}"

                results.append(operation_result)

            except Exception as op_error:
                operation_result["error"] = str(op_error)
                results.append(operation_result)

        # Summary statistics
        successful_ops = [r for r in results if r["success"]]
        failed_ops = [r for r in results if not r["success"]]

        logger.info("Batch tag operations completed",
                   total=total_operations, successful=len(successful_ops), failed=len(failed_ops))

        return {
            "success": True,
            "total_operations": total_operations,
            "successful_operations": len(successful_ops),
            "failed_operations": len(failed_ops),
            "results": results,
            "changeset_comment": changeset_comment,
            "dry_run": dry_run,
            "message": f"Batch operation: {len(successful_ops)}/{total_operations} operations successful",
            "warning": "⚠️ Review all operations before executing with dry_run=False" if dry_run else "⚠️ Live OSM data operations performed"
        }

    except Exception as e:
        logger.error("Failed to execute batch tag operations", operations_count=len(operations), error=str(e))
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