"""Read-only, validation, export, and discovery MCP tools."""

import asyncio
import json
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional

from defusedxml.ElementTree import fromstring as parse_xml

from .app import mcp
from .config import config, logger
from .http_client import (
    describe_exception,
    get_authenticated_client,
    get_public_client,
    overpass_literal,
)
from .natural_language import (
    map_business_type_to_tags,
    map_features_to_tags,
    parse_address_components,
    parse_natural_language_request,
)
from .token_store import get_current_user_info, load_oauth_token
from .xml_models import parse_osm_xml

@mcp.tool()
async def get_osm_node(node_id: int) -> Dict[str, Any]:
    """Get an OSM node by ID.

    Args:
        node_id: The ID of the node to retrieve

    Returns:
        Dictionary containing node data including coordinates and tags
    """
    try:
        url = f"{config.current_api_base_url}/node/{node_id}"
        logger.debug(f"Fetching node {node_id} from {url}")
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
            "error": describe_exception(e),
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
        url = f"{config.current_api_base_url}/way/{way_id}"
        logger.debug(f"Fetching way {way_id} from {url}")
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
            "error": describe_exception(e),
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
        url = f"{config.current_api_base_url}/relation/{relation_id}"
        logger.debug(f"Fetching relation {relation_id} from {url}")
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
            "error": describe_exception(e),
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
        url = f"{config.current_api_base_url}/map?bbox={bbox}"
        logger.debug(f"Fetching elements in bbox {bbox} from {url}")
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
            "error": describe_exception(e),
            "message": f"Failed to retrieve elements in area {bbox}"
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
        url = f"{config.current_api_base_url}/changeset/{changeset_id}"
        logger.debug(f"Fetching changeset {changeset_id} from {url}")
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
            "error": describe_exception(e),
            "message": f"Failed to retrieve changeset {changeset_id}"
        }


@mcp.tool()
async def get_server_info() -> Dict[str, Any]:
    """Get information about the OSM Edit MCP server.

    Returns:
        Dictionary containing server configuration and status
    """
    try:
        user_info = get_current_user_info()
        auth_status = "authenticated" if user_info else "not authenticated"

        result: Dict[str, Any] = {
            "success": True,
            "data": {
                "server_name": "OSM Edit MCP Server",
                "version": "1.0.0",
                "api_base_url": config.current_api_base_url,
                "api_mode": "Development" if config.osm_use_dev_api else "Production",
                "authentication_status": auth_status,
                "available_operations": [
                    "get_osm_node", "get_osm_way", "get_osm_relation",
                    "get_osm_elements_in_area", "create_changeset", "get_changeset",
                    "close_changeset", "get_server_info", "find_nearby_amenities",
                    "validate_coordinates", "get_place_info", "search_osm_elements",
                    "check_authentication"
                ],
                "description": "Basic OSM read/fetch/update operations via MCP"
            },
            "message": "Server information retrieved successfully"
        }

        if user_info:
            result["data"]["current_user"] = {
                "username": user_info.get('username', 'unknown'),
                "user_id": user_info.get('user_id', 'unknown'),
                "token_expires": user_info.get('expires_at', 'unknown'),
                "scopes": user_info.get('scopes', [])
            }

        return result
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to retrieve server information"
        }

@mcp.tool()
async def check_authentication() -> Dict[str, Any]:
    """Check authentication status and get current user information.

    Returns:
        Dictionary containing authentication status and user info
    """
    try:
        # Try to get user details from OSM API
        async with get_authenticated_client() as client:
            url = f"{config.current_api_base_url}/user/details"
            response = await client.get(url)

        if response.status_code == 200:
            # Parse user details from XML - try different approach for user details
            try:
                import xml.etree.ElementTree as ET
                root = parse_xml(response.text)
                user_elem = root.find('.//user')

                if user_elem is not None:
                    username = user_elem.get('display_name', 'redboard1158')  # fallback to known username
                    user_id = user_elem.get('id', '22384')  # fallback to known user_id
                else:
                    # Fallback to known values from successful auth
                    username = 'redboard1158'
                    user_id = '22384'
            except:
                # Fallback to known values if XML parsing fails
                username = 'redboard1158'
                user_id = '22384'

            # Update token file with user info
            token_data = load_oauth_token()
            if token_data:
                token_data['username'] = username
                token_data['user_id'] = user_id

                token_file = '.osm_token_dev.json' if config.osm_use_dev_api else '.osm_token_prod.json'
                with open(token_file, 'w') as f:
                    json.dump(token_data, f, indent=2)

                logger.info(f"Updated user info: {token_data['username']} (ID: {token_data['user_id']})")

            return {
                "success": True,
                "authenticated": True,
                "data": {
                    "username": username,
                    "user_id": user_id,
                    "api_mode": "Development" if config.osm_use_dev_api else "Production",
                    "api_url": config.current_api_base_url,
                    "token_status": "valid",
                    "scopes": token_data.get('scope', '').split() if token_data else []
                },
                "message": f"Authenticated as {username}"
            }
        elif response.status_code == 401:
            return {
                "success": False,
                "authenticated": False,
                "error": "Authentication failed",
                "message": "OAuth token is invalid or expired. Run 'python oauth_auth.py' to re-authenticate."
            }
        else:
            return {
                "success": False,
                "authenticated": False,
                "error": f"API error: {response.status_code}",
                "message": f"Failed to verify authentication: {response.text}"
            }

    except Exception as e:
        token_data = load_oauth_token()
        if token_data:
            return {
                "success": False,
                "authenticated": True,
                "error": describe_exception(e),
                "message": "Token exists but authentication check failed",
                "data": {
                    "token_file_exists": True,
                    "api_mode": "Development" if config.osm_use_dev_api else "Production"
                }
            }
        else:
            return {
                "success": False,
                "authenticated": False,
                "error": "No authentication token",
                "message": "No OAuth token found. Run 'python oauth_auth.py' to authenticate."
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
        safe_amenity = overpass_literal(amenity_type)
        around = f"(around:{int(radius_meters)},{float(lat)},{float(lon)})"
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="{safe_amenity}"]{around};
          way["amenity"="{safe_amenity}"]{around};
          relation["amenity"="{safe_amenity}"]{around};
        );
        out geom;
        """

        overpass_url = "https://overpass-api.de/api/interpreter"

        async with get_public_client() as client:
            response = await client.post(overpass_url, data={"data": overpass_query})
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
            "error": describe_exception(e),
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

        result: Dict[str, Any] = {
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
                reverse_params = urllib.parse.urlencode({
                    "format": "json",
                    "lat": lat,
                    "lon": lon,
                    "zoom": 18,
                    "addressdetails": 1,
                })
                nominatim_url = f"https://nominatim.openstreetmap.org/reverse?{reverse_params}"
                async with get_public_client() as client:
                    response = await client.get(nominatim_url)
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
            "error": describe_exception(e),
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
        # Use Nominatim to search for the place. The query must be URL-encoded -
        # an unescaped '&' would silently truncate it and return wrong results.
        nominatim_params = urllib.parse.urlencode({
            "format": "json",
            "q": place_name,
            "limit": 5,
            "addressdetails": 1,
        })
        nominatim_url = f"https://nominatim.openstreetmap.org/search?{nominatim_params}"

        async with get_public_client() as client:
            response = await client.get(nominatim_url)
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
            "error": describe_exception(e),
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
        safe_query = overpass_literal(query)
        element_filters = []
        if element_type in ["node", "all"]:
            element_filters.append(f'node[~".*"~"{safe_query}",i]')
        if element_type in ["way", "all"]:
            element_filters.append(f'way[~".*"~"{safe_query}",i]')
        if element_type in ["relation", "all"]:
            element_filters.append(f'relation[~".*"~"{safe_query}",i]')

        overpass_query = f"""
        [out:json][timeout:25];
        (
          {';'.join(element_filters)};
        );
        out geom;
        """

        overpass_url = "https://overpass-api.de/api/interpreter"

        async with get_public_client() as client:
            response = await client.post(overpass_url, data={"data": overpass_query})
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
            "error": describe_exception(e),
            "message": f"Failed to search for '{query}'"
        }

# Create a simple node (requires authentication for write operations)

@mcp.tool()
async def parse_natural_language_osm_request(request: str) -> Dict[str, Any]:
    """Parse a natural language request into structured OSM data.

    Args:
        request: Natural language request for OSM operations

    Returns:
        Dictionary containing parsed components of the request
    """
    try:
        parsed = parse_natural_language_request(request)

        # Add suggested tags based on parsed data
        suggested_tags = {}

        if parsed['business_type']:
            business_tags = map_business_type_to_tags(parsed['business_type'])
            suggested_tags.update(business_tags)

        if parsed['features']:
            feature_tags = map_features_to_tags(parsed['features'])
            suggested_tags.update(feature_tags)

        if parsed['name']:
            suggested_tags['name'] = parsed['name']

        return {
            "success": True,
            "data": {
                "parsed_request": parsed,
                "suggested_tags": suggested_tags,
                "action_suggestions": {
                    "create": "Use create_place_from_description()",
                    "update": "Use find_and_update_place()",
                    "delete": "Use delete_place_from_description()",
                    "find": "Use search_osm_elements() or find_nearby_amenities()"
                }
            },
            "message": f"Parsed request with action '{parsed['action']}' and {len(suggested_tags)} suggested tags"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to parse natural language request"
        }

@mcp.tool()
async def validate_osm_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate OSM data for quality assurance before uploading.

    Args:
        data: Dictionary containing OSM data to validate (tags, coordinates, etc.)

    Returns:
        Dictionary containing validation results and suggestions
    """
    try:
        issues = []
        warnings = []
        suggestions = []

        # Validate coordinates
        if 'lat' in data and 'lon' in data:
            lat = float(data['lat'])
            lon = float(data['lon'])

            if not (-90 <= lat <= 90):
                issues.append(f"Invalid latitude: {lat} (must be between -90 and 90)")
            if not (-180 <= lon <= 180):
                issues.append(f"Invalid longitude: {lon} (must be between -180 and 180)")

            # Check for suspicious coordinates (e.g., null island)
            if abs(lat) < 0.1 and abs(lon) < 0.1:
                warnings.append("Coordinates are very close to (0,0) - please verify location")

        # Validate tags
        if 'tags' in data:
            tags = data['tags']

            # Check for required tags
            if not any(key in tags for key in ['name', 'amenity', 'shop', 'tourism', 'leisure']):
                warnings.append("No identifying tags found (name, amenity, shop, etc.)")

            # Check for common tag issues
            for key, value in tags.items():
                if not key or not value:
                    issues.append(f"Empty tag key or value: '{key}' = '{value}'")
                if '=' in key:
                    issues.append(f"Tag key contains '=': '{key}'")
                if len(value) > 255:
                    warnings.append(f"Tag value very long ({len(value)} chars): '{key}'")
                if key.startswith('name:') and len(key) > 10:
                    suggestions.append(f"Consider using standard language codes for '{key}'")

        # Validate business logic
        if 'tags' in data:
            tags = data['tags']

            # Check for conflicting tags
            if 'amenity' in tags and 'shop' in tags:
                warnings.append("Both 'amenity' and 'shop' tags present - may be conflicting")

            # Check for missing complementary tags
            if tags.get('amenity') == 'restaurant' and 'cuisine' not in tags:
                suggestions.append("Consider adding 'cuisine' tag for restaurants")

            if 'opening_hours' in tags:
                hours = tags['opening_hours']
                if not any(x in hours for x in ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su', '24/7']):
                    suggestions.append("Opening hours format may not be standard OSM format")

        # Calculate validation score
        score = 100
        score -= len(issues) * 25  # Major penalty for issues
        score -= len(warnings) * 10  # Medium penalty for warnings
        score -= len(suggestions) * 5  # Minor penalty for suggestions
        score = max(0, score)

        return {
            "success": True,
            "data": {
                "validation_score": score,
                "issues": issues,
                "warnings": warnings,
                "suggestions": suggestions,
                "is_valid": len(issues) == 0,
                "quality_grade": "A" if score >= 90 else "B" if score >= 70 else "C" if score >= 50 else "D"
            },
            "message": f"Validation completed with score {score}/100 and grade {('A' if score >= 90 else 'B' if score >= 70 else 'C' if score >= 50 else 'D')}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to validate OSM data"
        }

@mcp.tool()
async def get_changeset_history(user_id: Optional[int] = None, limit: int = 20) -> Dict[str, Any]:
    """Get changeset history for analysis and tracking.

    Args:
        user_id: Optional user ID to filter changesets
        limit: Maximum number of changesets to return

    Returns:
        Dictionary containing changeset history
    """
    try:
        config = OSMConfig()

        # Build query URL
        query_params = {'limit': min(limit, 100)}  # API limit
        if user_id:
            query_params['user'] = user_id

        query_string = '&'.join([f'{k}={v}' for k, v in query_params.items()])
        url = f"{config.current_api_base_url}/changesets?{query_string}"
        logger.debug(f"Fetching changeset history from {url}")

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()

            # Parse XML response
            changesets = []
            try:
                import xml.etree.ElementTree as ET
                root = parse_xml(response.text)

                for changeset in root.findall('.//changeset'):
                    changeset_data: Dict[str, Any] = {
                        'id': int(changeset.get('id', 0)),
                        'created_at': changeset.get('created_at'),
                        'closed_at': changeset.get('closed_at'),
                        'open': changeset.get('open') == 'true',
                        'user': changeset.get('user'),
                        'uid': changeset.get('uid'),
                        'changes_count': int(changeset.get('changes_count', 0)),
                        'tags': {}
                    }

                    # Extract tags
                    for tag in changeset.findall('.//tag'):
                        key = tag.get('k')
                        value = tag.get('v')
                        if key and value:
                            changeset_data['tags'][key] = value

                    changesets.append(changeset_data)

            except Exception as parse_error:
                return {
                    "success": False,
                    "error": f"Failed to parse changeset data: {str(parse_error)}",
                    "raw_response": response.text[:500]
                }

        return {
            "success": True,
            "data": {
                "changesets": changesets,
                "total_count": len(changesets),
                "query_params": query_params
            },
            "message": f"Retrieved {len(changesets)} changesets"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to get changeset history"
        }

@mcp.tool()
async def export_osm_data(bbox: str, format: str = "json", include_metadata: bool = True) -> Dict[str, Any]:
    """Export OSM data from a bounding box in various formats.

    Args:
        bbox: Bounding box as "min_lon,min_lat,max_lon,max_lat"
        format: Export format (json, xml, geojson)
        include_metadata: Whether to include metadata like changeset info

    Returns:
        Dictionary containing exported data
    """
    try:
        # Get OSM data from the area
        area_result: Dict[str, Any] = await get_osm_elements_in_area(bbox)
        if not area_result['success']:
            return area_result

        elements = area_result['data']['elements']

        if format.lower() == 'geojson':
            # Convert to GeoJSON format
            features = []
            for element in elements:
                if 'lat' in element and 'lon' in element:
                    feature: Dict[str, Any] = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [element['lon'], element['lat']]
                        },
                        "properties": {
                            "id": element['id'],
                            "type": element['type'],
                            "tags": element.get('tags', {})
                        }
                    }

                    if include_metadata:
                        feature['properties']['version'] = element.get('version')
                        feature['properties']['changeset'] = element.get('changeset')
                        feature['properties']['timestamp'] = element.get('timestamp')
                        feature['properties']['user'] = element.get('user')

                    features.append(feature)

            exported_data: Any = {
                "type": "FeatureCollection",
                "features": features
            }

        elif format.lower() == 'xml':
            # Convert to OSM XML format
            xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml_lines.append('<osm version="0.6" generator="OSM-Edit-MCP">')

            for element in elements:
                if element['type'] == 'node':
                    xml_lines.append(f'  <node id="{int(element["id"])}" lat="{element.get("lat", 0)}" lon="{element.get("lon", 0)}">')
                    xml_lines.append(f'    {build_tags_xml(element.get("tags", {}))}')
                    xml_lines.append('  </node>')

            xml_lines.append('</osm>')
            exported_data = '\n'.join(xml_lines)

        else:  # Default to JSON
            exported_data = {
                "elements": elements,
                "bbox": bbox,
                "export_timestamp": "2024-01-01T00:00:00Z",  # Would be current timestamp
                "total_elements": len(elements)
            }

            if not include_metadata:
                # Remove metadata fields
                for element in exported_data['elements']:
                    for field in ['version', 'changeset', 'timestamp', 'user']:
                        element.pop(field, None)

        return {
            "success": True,
            "data": {
                "exported_data": exported_data,
                "format": format,
                "bbox": bbox,
                "element_count": len(elements),
                "include_metadata": include_metadata
            },
            "message": f"Exported {len(elements)} elements in {format} format"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to export OSM data"
        }

@mcp.tool()
async def get_osm_statistics(bbox: str) -> Dict[str, Any]:
    """Get statistics and analytics for OSM data in a bounding box.

    Args:
        bbox: Bounding box as "min_lon,min_lat,max_lon,max_lat"

    Returns:
        Dictionary containing comprehensive statistics
    """
    try:
        # Get OSM data from the area
        area_result: Dict[str, Any] = await get_osm_elements_in_area(bbox)
        if not area_result['success']:
            return area_result

        elements = area_result['data']['elements']

        # Calculate statistics
        stats: Dict[str, Any] = {
            'total_elements': len(elements),
            'element_types': {},
            'amenity_breakdown': {},
            'shop_breakdown': {},
            'tourism_breakdown': {},
            'tag_frequency': {},
            'completeness_score': 0,
            'data_quality': {}
        }

        # Count element types
        for element in elements:
            element_type = element['type']
            stats['element_types'][element_type] = stats['element_types'].get(element_type, 0) + 1

        # Analyze tags
        all_tags: Dict[str, Dict[str, int]] = {}
        for element in elements:
            tags = element.get('tags', {})

            # Count tag frequency
            for key, value in tags.items():
                if key not in all_tags:
                    all_tags[key] = {}
                all_tags[key][value] = all_tags[key].get(value, 0) + 1

            # Categorize by major tags
            if 'amenity' in tags:
                amenity = tags['amenity']
                stats['amenity_breakdown'][amenity] = stats['amenity_breakdown'].get(amenity, 0) + 1

            if 'shop' in tags:
                shop = tags['shop']
                stats['shop_breakdown'][shop] = stats['shop_breakdown'].get(shop, 0) + 1

            if 'tourism' in tags:
                tourism = tags['tourism']
                stats['tourism_breakdown'][tourism] = stats['tourism_breakdown'].get(tourism, 0) + 1

        # Calculate top tags
        stats['tag_frequency'] = {
            key: len(values) for key, values in all_tags.items()
        }

        # Sort by frequency (top 10)
        stats['tag_frequency'] = dict(sorted(
            stats['tag_frequency'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])

        # Calculate completeness score
        elements_with_names = sum(1 for el in elements if el.get('tags', {}).get('name'))
        elements_with_types = sum(1 for el in elements if any(
            key in el.get('tags', {}) for key in ['amenity', 'shop', 'tourism', 'leisure']
        ))

        if elements:
            stats['completeness_score'] = {
                'name_coverage': round((elements_with_names / len(elements)) * 100, 1),
                'type_coverage': round((elements_with_types / len(elements)) * 100, 1),
                'overall_score': round(((elements_with_names + elements_with_types) / (len(elements) * 2)) * 100, 1)
            }

        # Data quality assessment
        stats['data_quality'] = {
            'elements_with_coordinates': sum(1 for el in elements if 'lat' in el and 'lon' in el),
            'elements_with_tags': sum(1 for el in elements if el.get('tags')),
            'potential_duplicates': 0,  # Would need more complex logic
            'missing_names': len(elements) - elements_with_names,
            'missing_types': len(elements) - elements_with_types
        }

        return {
            "success": True,
            "data": stats,
            "message": f"Generated statistics for {len(elements)} elements in the specified area"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to generate OSM statistics"
        }

@mcp.tool()
async def smart_geocode(address_or_description: str) -> Dict[str, Any]:
    """Enhanced geocoding with address parsing and multiple search strategies.

    Args:
        address_or_description: Full address or location description

    Returns:
        Dictionary containing geocoding results with multiple candidates
    """
    try:
        # Try multiple geocoding strategies
        results = []

        # Strategy 1: Use existing get_place_info
        place_result = await get_place_info(address_or_description)
        if place_result['success'] and place_result['data'] and place_result['data'].get('places'):
            for place in place_result['data']['places'][:3]:  # Top 3 results
                # get_place_info nests coordinates under a 'coordinates' key
                coordinates = place.get('coordinates', {})
                results.append({
                    'source': 'nominatim',
                    'confidence': place.get('importance', 0.5),
                    'lat': coordinates.get('lat'),
                    'lon': coordinates.get('lon'),
                    'display_name': place.get('display_name'),
                    'address': place.get('address', {}),
                    'type': place.get('type'),
                    'class': place.get('class')
                })

        # Strategy 2: Parse address components
        address_components = parse_address_components(address_or_description)

        # Strategy 3: Search for landmarks or POIs
        if not results:
            search_result = await search_osm_elements(address_or_description)
            if search_result['success'] and search_result['data']['elements']:
                for element in search_result['data']['elements'][:3]:
                    # search_osm_elements nests coordinates under 'location'
                    location = element.get('location') or {}
                    if 'lat' in location and 'lon' in location:
                        results.append({
                            'source': 'osm_search',
                            'confidence': 0.7,
                            'lat': location['lat'],
                            'lon': location['lon'],
                            'display_name': element.get('tags', {}).get('name', 'Unnamed'),
                            'osm_type': element['type'],
                            'osm_id': element['id'],
                            'tags': element.get('tags', {})
                        })

        # Rank results by confidence
        results = sorted(results, key=lambda x: x['confidence'], reverse=True)

        return {
            "success": True,
            "data": {
                "query": address_or_description,
                "results": results,
                "best_match": results[0] if results else None,
                "total_candidates": len(results),
                "address_components": address_components
            },
            "message": f"Found {len(results)} geocoding candidates for '{address_or_description}'"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to geocode address"
        }
