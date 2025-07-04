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
            "get_osm_node", "get_osm_way", "get_osm_relation",
            "get_osm_elements_in_area", "create_changeset", "get_changeset",
            "close_changeset", "get_server_info", "find_nearby_amenities",
            "validate_coordinates", "get_place_info", "search_osm_elements"
        ],
        "description": "Basic OSM read/fetch/update operations via MCP"
    }

@mcp.tool()
async def find_nearby_amenities(lat: float, lon: float, radius_meters: int = 1000, amenity_type: str = "restaurant") -> Dict[str, Any]:
    """Find nearby amenities around a location using Overpass API.

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        radius_meters: Search radius in meters (default: 1000)
        amenity_type: Type of amenity to search for (restaurant, cafe, hospital, etc.)

    Returns:
        Dictionary containing nearby amenities with their details
    """
    try:
        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {
                "success": False,
                "error": "Invalid coordinates",
                "message": "Latitude must be between -90 and 90, longitude between -180 and 180"
            }

        # Overpass API query
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="{amenity_type}"](around:{radius_meters},{lat},{lon});
          way["amenity"="{amenity_type}"](around:{radius_meters},{lat},{lon});
          relation["amenity"="{amenity_type}"](around:{radius_meters},{lat},{lon});
        );
        out geom;
        """

        overpass_url = "https://overpass-api.de/api/interpreter"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                overpass_url,
                data=overpass_query,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            data = response.json()

            # Process results
            amenities = []
            for element in data.get("elements", []):
                amenity_info = {
                    "id": element.get("id"),
                    "type": element.get("type"),
                    "tags": element.get("tags", {}),
                }

                # Add location info
                if element.get("type") == "node":
                    amenity_info["location"] = {
                        "lat": element.get("lat"),
                        "lon": element.get("lon")
                    }
                elif element.get("geometry"):
                    # For ways and relations, use center of geometry
                    coords = element["geometry"]
                    if coords:
                        avg_lat = sum(c["lat"] for c in coords) / len(coords)
                        avg_lon = sum(c["lon"] for c in coords) / len(coords)
                        amenity_info["location"] = {"lat": avg_lat, "lon": avg_lon}

                amenities.append(amenity_info)

            return {
                "success": True,
                "data": {
                    "query_location": {"lat": lat, "lon": lon},
                    "radius_meters": radius_meters,
                    "amenity_type": amenity_type,
                    "count": len(amenities),
                    "amenities": amenities
                },
                "message": f"Found {len(amenities)} {amenity_type}s within {radius_meters}m"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to find nearby {amenity_type}s"
        }

@mcp.tool()
async def validate_coordinates(lat: float, lon: float) -> Dict[str, Any]:
    """Validate coordinates and provide information about the location.

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate

    Returns:
        Dictionary containing validation results and location information
    """
    try:
        # Basic validation
        is_valid = (-90 <= lat <= 90) and (-180 <= lon <= 180)

        result = {
            "success": True,
            "data": {
                "coordinates": {"lat": lat, "lon": lon},
                "is_valid": is_valid,
                "validation_details": {
                    "latitude_valid": -90 <= lat <= 90,
                    "longitude_valid": -180 <= lon <= 180,
                    "latitude_range": "[-90, 90]",
                    "longitude_range": "[-180, 180]"
                }
            },
            "message": f"Coordinates are {'valid' if is_valid else 'invalid'}: {lat}, {lon}"
        }

        if is_valid:
            # Add geographic information
            result["data"]["geographic_info"] = {
                "hemisphere_lat": "North" if lat >= 0 else "South",
                "hemisphere_lon": "East" if lon >= 0 else "West",
                "quadrant": f"{'North' if lat >= 0 else 'South'}{'east' if lon >= 0 else 'west'}"
            }

            # Try to get reverse geocoding from OSM Nominatim
            try:
                nominatim_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
                async with httpx.AsyncClient() as client:
                    response = await client.get(nominatim_url, headers={"User-Agent": "OSM-Edit-MCP-Server"})
                    if response.status_code == 200:
                        location_data = response.json()
                        result["data"]["location_info"] = {
                            "display_name": location_data.get("display_name", "Unknown location"),
                            "address": location_data.get("address", {}),
                            "osm_type": location_data.get("osm_type"),
                            "osm_id": location_data.get("osm_id")
                        }
            except:
                pass  # Reverse geocoding is optional

            result["message"] = f"Coordinates are valid: {lat}, {lon}"
        else:
            result["message"] = f"Invalid coordinates: {lat}, {lon}"

        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to validate coordinates"
        }

@mcp.tool()
async def get_place_info(place_name: str) -> Dict[str, Any]:
    """Get information about a place by name using OSM Nominatim.

    Args:
        place_name: Name of the place to search for

    Returns:
        Dictionary containing place information and coordinates
    """
    try:
        # Use Nominatim to search for the place
        nominatim_url = f"https://nominatim.openstreetmap.org/search?format=json&q={place_name}&limit=5&addressdetails=1"

        async with httpx.AsyncClient() as client:
            response = await client.get(nominatim_url, headers={"User-Agent": "OSM-Edit-MCP-Server"})
            response.raise_for_status()
            places = response.json()

            if not places:
                return {
                    "success": False,
                    "error": "No places found",
                    "message": f"No results found for '{place_name}'"
                }

            # Process results
            results = []
            for place in places:
                place_info = {
                    "display_name": place.get("display_name"),
                    "coordinates": {
                        "lat": float(place.get("lat", 0)),
                        "lon": float(place.get("lon", 0))
                    },
                    "osm_type": place.get("osm_type"),
                    "osm_id": place.get("osm_id"),
                    "place_type": place.get("type"),
                    "category": place.get("category"),
                    "address": place.get("address", {}),
                    "importance": place.get("importance", 0),
                    "bounding_box": place.get("boundingbox", [])
                }
                results.append(place_info)

            return {
                "success": True,
                "data": {
                    "query": place_name,
                    "count": len(results),
                    "places": results
                },
                "message": f"Found {len(results)} places for '{place_name}'"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to search for place '{place_name}'"
        }

@mcp.tool()
async def search_osm_elements(query: str, element_type: str = "all") -> Dict[str, Any]:
    """Search for OSM elements using Overpass API with a text query.

    Args:
        query: Search query (e.g., "coffee shop", "hospital", "park")
        element_type: Type of element to search for (node, way, relation, or all)

    Returns:
        Dictionary containing search results
    """
    try:
        # Build Overpass query based on element type
        element_filters = []
        if element_type in ["node", "all"]:
            element_filters.append(f'node[~".*"~"{query}",i]')
        if element_type in ["way", "all"]:
            element_filters.append(f'way[~".*"~"{query}",i]')
        if element_type in ["relation", "all"]:
            element_filters.append(f'relation[~".*"~"{query}",i]')

        overpass_query = f"""
        [out:json][timeout:25];
        (
          {';'.join(element_filters)};
        );
        out geom;
        """

        overpass_url = "https://overpass-api.de/api/interpreter"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                overpass_url,
                data=overpass_query,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            data = response.json()

            # Process results
            elements = []
            for element in data.get("elements", [])[:20]:  # Limit to first 20 results
                element_info = {
                    "id": element.get("id"),
                    "type": element.get("type"),
                    "tags": element.get("tags", {}),
                }

                # Add location info
                if element.get("type") == "node":
                    element_info["location"] = {
                        "lat": element.get("lat"),
                        "lon": element.get("lon")
                    }
                elif element.get("geometry"):
                    coords = element["geometry"]
                    if coords:
                        avg_lat = sum(c["lat"] for c in coords) / len(coords)
                        avg_lon = sum(c["lon"] for c in coords) / len(coords)
                        element_info["location"] = {"lat": avg_lat, "lon": avg_lon}

                elements.append(element_info)

            return {
                "success": True,
                "data": {
                    "query": query,
                    "element_type": element_type,
                    "count": len(elements),
                    "elements": elements
                },
                "message": f"Found {len(elements)} elements matching '{query}'"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to search for '{query}'"
        }

# Create a simple node (requires authentication for write operations)
@mcp.tool()
async def create_osm_node(lat: float, lon: float, tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Create a new OSM node (requires authentication).

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        tags: Dictionary of tags for the node
        changeset_id: ID of the changeset to add this node to

    Returns:
        Dictionary containing the new node ID and status
    """
    try:
        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {
                "success": False,
                "error": "Invalid coordinates",
                "message": "Latitude must be between -90 and 90, longitude between -180 and 180"
            }

        # Create node XML
        node_xml = f'<osm><node changeset="{changeset_id}" lat="{lat}" lon="{lon}">'
        for key, value in tags.items():
            node_xml += f'<tag k="{key}" v="{value}"/>'
        node_xml += '</node></osm>'

        # Note: This would require OAuth authentication for actual creation
        # For now, return a mock response
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Node creation requires OAuth authentication. This is a read-only demo.",
            "would_create": {
                "coordinates": {"lat": lat, "lon": lon},
                "tags": tags,
                "changeset_id": changeset_id
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to create node"
        }
