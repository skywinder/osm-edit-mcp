"""Read-only, validation, export, and discovery MCP tools."""

import asyncio
import json
import re
import urllib.parse
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations

from .app import mcp
from .auth import _parse_identity, _parse_permissions
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
from .nearby import bounded_integer, results, safe_text, selectors, validate_point
from .overpass import OverpassExecutor
from .token_store import get_current_user_info, load_oauth_token
from .xml_models import build_tags_xml, parse_osm_xml

_overpass = OverpassExecutor()
execute_overpass = _overpass.execute

ReadFunction = TypeVar("ReadFunction", bound=Callable[..., Any])


def _read_tool(function: ReadFunction) -> ReadFunction:
    return cast(
        ReadFunction,
        mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )(function),
    )


@_read_tool
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
        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved node {node_id}",
            }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to retrieve node {node_id}",
        }


@_read_tool
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
        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved way {way_id}",
            }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to retrieve way {way_id}",
        }


@_read_tool
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
        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved relation {relation_id}",
            }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to retrieve relation {relation_id}",
        }


@_read_tool
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
        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved elements in bounding box {bbox}",
            }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to retrieve elements in area {bbox}",
        }


@_read_tool
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
        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            parsed_data = parse_osm_xml(response.text)
            return {
                "success": True,
                "data": parsed_data,
                "message": f"Retrieved changeset {changeset_id}",
            }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to retrieve changeset {changeset_id}",
        }


@_read_tool
async def get_server_info() -> Dict[str, Any]:
    """Get information about the OSM Edit MCP server.

    Returns:
        Dictionary containing server configuration and status
    """
    try:
        user_info = get_current_user_info()
        auth_status = "token configured (unverified)" if user_info else "not configured"

        result: Dict[str, Any] = {
            "success": True,
            "data": {
                "server_name": "OSM Edit MCP Server",
                "version": config.mcp_server_version,
                "api_base_url": config.current_api_base_url,
                "api_mode": config.api_environment.title(),
                "authentication_status": auth_status,
                "available_safe_edit_operations": [
                    "get_edit_capabilities",
                    "inspect_map_context",
                    "analyze_gpx_track",
                    "create_track_selection",
                    "match_track_selection",
                    "suggest_track_road_candidates",
                    "preview_track_road_edit",
                    "apply_osm_edit",
                    "list_edit_proposals",
                    "verify_osm_edit",
                ],
                "raw_write_tools_registered": config.direct_write_tools_enabled,
                "production_confirmation": ("MCP elicitation bound to proposal digest"),
                "description": (
                    "OSM read operations and proposal-based GPX road editing via MCP"
                ),
            },
            "message": "Server information retrieved successfully",
        }

        if user_info:
            result["data"]["cached_user_hint"] = {
                "username": user_info.get("username", "unknown"),
                "user_id": user_info.get("user_id", "unknown"),
                "token_expires": user_info.get("expires_at", "unknown"),
                "scopes": user_info.get("scopes", []),
            }

        return result
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to retrieve server information",
        }


@_read_tool
async def check_authentication() -> Dict[str, Any]:
    """Check authentication status and get current user information.

    Returns:
        Dictionary containing authentication status and user info
    """
    token_data = load_oauth_token()
    if not token_data or not token_data.get("access_token"):
        return {
            "success": False,
            "authenticated": False,
            "error": "No authentication token",
            "message": "No OAuth token found. Run 'python oauth_auth.py' to authenticate.",
        }
    try:
        async with get_authenticated_client() as client:
            details = await client.get(f"{config.current_api_base_url}/user/details")
            if details.status_code != 200:
                return {
                    "success": False,
                    "authenticated": False,
                    "error": f"API error: {details.status_code}",
                    "message": "OSM rejected the OAuth token",
                }
            identity = _parse_identity(details.text)
            permissions_response = await client.get(
                f"{config.current_api_base_url}/permissions"
            )
            permissions = (
                sorted(_parse_permissions(permissions_response.text))
                if permissions_response.status_code == 200
                else []
            )
        return {
            "success": True,
            "authenticated": True,
            "data": {
                **identity,
                "api_mode": config.api_environment.title(),
                "api_url": config.current_api_base_url,
                "token_status": "valid",
                "permissions": permissions,
            },
            "message": f"Authenticated as {identity['username']}",
        }
    except Exception as exc:
        return {
            "success": False,
            "authenticated": False,
            "error": describe_exception(exc),
            "message": "Token exists but live authentication could not be verified",
        }


@_read_tool
async def search_nearby_places(
    lat: float,
    lon: float,
    radius_meters: int = 1000,
    categories: Optional[List[str]] = None,
    limit: int = 20,
    tag_filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Search within 1–10000m. Categories are OR; exact tag_filters are AND
    constraints on every category (or used alone). No arbitrary QL or regex.
    Returns up to 100 places, deduplicated and sorted by straight-line distance
    to node / Overpass bounding-box center, not walking routes. Polygon centers
    may lie outside the radius. Unknown categories return available names.
    """
    try:
        validate_point(lat, lon)
        bounded_integer(radius_meters, "radius_meters", 10000)
        bounded_integer(limit, "limit", 100)
        groups = selectors(categories, tag_filters)
        clauses = [
            f"nwr{tags}(around:{radius_meters},{float(lat)},{float(lon)});"
            for tags in groups
        ]
        query = "[out:json][timeout:25];(" + "".join(clauses) + ");out center tags;"
        data = results(await execute_overpass(query), lat, lon, limit)
        data.update(
            query_location={"lat": lat, "lon": lon},
            radius_meters=radius_meters,
            distance_reference="query_location",
        )
        return {"success": True, "data": data, "message": "Nearby places retrieved"}
    except Exception as exc:
        return {
            "success": False,
            "error": describe_exception(exc),
            "message": "Nearby search failed",
        }


@_read_tool
async def find_nearby_amenities(
    lat: float,
    lon: float,
    radius_meters: Optional[int] = None,
    amenity_type: str = "restaurant",
    radius: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Compatibility amenity-only search. radius aliases radius_meters; conflicts
    fail explicitly. Omitted radii default to 1000m. For museums/parks use
    search_nearby_places categories instead of inventing amenity tags.
    """
    if radius is not None and radius_meters is not None and radius != radius_meters:
        return {
            "success": False,
            "error": "Conflicting radius and radius_meters",
            "message": "Choose one radius",
        }
    effective = (
        radius
        if radius is not None
        else radius_meters if radius_meters is not None else 1000
    )
    result = await search_nearby_places(
        lat, lon, effective, limit=limit, tag_filters={"amenity": amenity_type}
    )
    if result["success"]:
        result["data"]["amenities"] = result["data"].pop("places")
        result["data"]["amenity_type"] = amenity_type
    return result


@_read_tool
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
                    "longitude_range": "[-180, 180]",
                },
            },
            "message": f"Coordinates are {'valid' if is_valid else 'invalid'}: {lat}, {lon}",
        }

        if is_valid:
            # Add geographic information
            result["data"]["geographic_info"] = {
                "hemisphere_lat": "North" if lat >= 0 else "South",
                "hemisphere_lon": "East" if lon >= 0 else "West",
                "quadrant": f"{'North' if lat >= 0 else 'South'}{'east' if lon >= 0 else 'west'}",
            }

            # Try to get reverse geocoding from OSM Nominatim
            try:
                reverse_params = urllib.parse.urlencode(
                    {
                        "format": "json",
                        "lat": lat,
                        "lon": lon,
                        "zoom": 18,
                        "addressdetails": 1,
                    }
                )
                nominatim_url = (
                    f"https://nominatim.openstreetmap.org/reverse?{reverse_params}"
                )
                async with get_public_client() as client:
                    response = await client.get(nominatim_url)
                    if response.status_code == 200:
                        location_data = response.json()
                        result["data"]["location_info"] = {
                            "display_name": location_data.get(
                                "display_name", "Unknown location"
                            ),
                            "address": location_data.get("address", {}),
                            "osm_type": location_data.get("osm_type"),
                            "osm_id": location_data.get("osm_id"),
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
            "message": "Failed to validate coordinates",
        }


@_read_tool
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
        nominatim_params = urllib.parse.urlencode(
            {
                "format": "json",
                "q": place_name,
                "limit": 5,
                "addressdetails": 1,
            }
        )
        nominatim_url = f"https://nominatim.openstreetmap.org/search?{nominatim_params}"

        async with get_public_client() as client:
            response = await client.get(nominatim_url)
            response.raise_for_status()
            places = response.json()

            if not places:
                return {
                    "success": False,
                    "error": "No places found",
                    "message": f"No results found for '{place_name}'",
                }

            # Process results
            results = []
            for place in places:
                place_info = {
                    "display_name": place.get("display_name"),
                    "coordinates": {
                        "lat": float(place.get("lat", 0)),
                        "lon": float(place.get("lon", 0)),
                    },
                    "osm_type": place.get("osm_type"),
                    "osm_id": place.get("osm_id"),
                    "place_type": place.get("type"),
                    "category": place.get("category"),
                    "address": place.get("address", {}),
                    "importance": place.get("importance", 0),
                    "bounding_box": place.get("boundingbox", []),
                }
                results.append(place_info)

            return {
                "success": True,
                "data": {"query": place_name, "count": len(results), "places": results},
                "message": f"Found {len(results)} places for '{place_name}'",
            }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to search for place '{place_name}'",
        }


@_read_tool
async def search_osm_elements(
    query: str,
    element_type: str = "all",
    bbox: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_meters: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Literal case-insensitive text search in multilingual name/alt_name/
    official_name tags (including :* variants) and amenity/tourism/leisure/
    historic/shop tags. Requires bbox (west,south,east,north, max 0.25 degrees
    each side) OR lat/lon/radius_meters (1–10000m). Never a global regex scan.
    Results sorted by straight-line distance from point or bbox center.
    """
    try:
        bounded_integer(limit, "limit", 100)
        if element_type not in ("all", "node", "way", "relation"):
            raise ValueError("element_type must be all, node, way or relation")
        safe_text(query)
        if bbox is not None:
            if any(v is not None for v in (lat, lon, radius_meters)):
                raise ValueError("Choose bbox OR lat/lon/radius_meters, not both")
            west, south, east, north = [float(v) for v in bbox.split(",")]
            validate_point(south, west)
            validate_point(north, east)
            if not (0 < east - west <= 0.25 and 0 < north - south <= 0.25):
                raise ValueError(
                    "bbox must be ordered west,south,east,north, with each span <= 0.25 degrees"
                )
            lat, lon = (south + north) / 2, (west + east) / 2
            scope = f"({south},{west},{north},{east})"
            reference = "bbox_center"
        else:
            if lat is None or lon is None or radius_meters is None:
                raise ValueError(
                    "Geographical scope required: supply bbox or lat, lon and radius_meters"
                )
            validate_point(lat, lon)
            bounded_integer(radius_meters, "radius_meters", 10000)
            scope = f"(around:{radius_meters},{float(lat)},{float(lon)})"
            reference = "query_location"
        literal = overpass_literal(re.escape(query))
        kind = "nwr" if element_type == "all" else element_type
        # Fixed name-family key regex; user input is only an escaped value.
        clauses = (
            f'{kind}[~"^(name|alt_name|official_name)(:.*)?$"~"{literal}",i]{scope};'
        )
        clauses += "".join(
            f'{kind}["{key}"~"{literal}",i]{scope};'
            for key in ("amenity", "tourism", "leisure", "historic", "shop")
        )
        data = results(
            await execute_overpass(
                "[out:json][timeout:25];(" + clauses + ");out center tags;"
            ),
            lat,
            lon,
            limit,
        )
        data["elements"] = data.pop("places")
        data.update(
            query=query,
            element_type=element_type,
            query_location={"lat": lat, "lon": lon},
            distance_reference=reference,
        )
        return {
            "success": True,
            "data": data,
            "message": "Scoped text search completed",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": describe_exception(exc),
            "message": "Scoped text search failed",
        }


@_read_tool
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

        if parsed["business_type"]:
            business_tags = map_business_type_to_tags(parsed["business_type"])
            suggested_tags.update(business_tags)

        if parsed["features"]:
            feature_tags = map_features_to_tags(parsed["features"])
            suggested_tags.update(feature_tags)

        if parsed["name"]:
            suggested_tags["name"] = parsed["name"]

        return {
            "success": True,
            "data": {
                "parsed_request": parsed,
                "suggested_tags": suggested_tags,
                "action_suggestions": {
                    "create": (
                        "No natural-language create tool is registered in the safe "
                        "profile; GPX road geometry must use the review-first prompt"
                    ),
                    "update": (
                        "No natural-language update tool is registered in the safe "
                        "profile; choose exact OSM IDs through the review workflow"
                    ),
                    "delete": "Natural-language deletion is not supported",
                    "find": "Use search_osm_elements() or find_nearby_amenities()",
                },
            },
            "message": f"Parsed request with action '{parsed['action']}' and {len(suggested_tags)} suggested tags",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to parse natural language request",
        }


@_read_tool
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
        if "lat" in data and "lon" in data:
            lat = float(data["lat"])
            lon = float(data["lon"])

            if not (-90 <= lat <= 90):
                issues.append(f"Invalid latitude: {lat} (must be between -90 and 90)")
            if not (-180 <= lon <= 180):
                issues.append(
                    f"Invalid longitude: {lon} (must be between -180 and 180)"
                )

            # Check for suspicious coordinates (e.g., null island)
            if abs(lat) < 0.1 and abs(lon) < 0.1:
                warnings.append(
                    "Coordinates are very close to (0,0) - please verify location"
                )

        # Validate tags
        if "tags" in data:
            tags = data["tags"]

            # Check for required tags
            if not any(
                key in tags for key in ["name", "amenity", "shop", "tourism", "leisure"]
            ):
                warnings.append("No identifying tags found (name, amenity, shop, etc.)")

            # Check for common tag issues
            for key, value in tags.items():
                if not key or not value:
                    issues.append(f"Empty tag key or value: '{key}' = '{value}'")
                if "=" in key:
                    issues.append(f"Tag key contains '=': '{key}'")
                if len(value) > 255:
                    warnings.append(
                        f"Tag value very long ({len(value)} chars): '{key}'"
                    )
                if key.startswith("name:") and len(key) > 10:
                    suggestions.append(
                        f"Consider using standard language codes for '{key}'"
                    )

        # Validate business logic
        if "tags" in data:
            tags = data["tags"]

            # Check for conflicting tags
            if "amenity" in tags and "shop" in tags:
                warnings.append(
                    "Both 'amenity' and 'shop' tags present - may be conflicting"
                )

            # Check for missing complementary tags
            if tags.get("amenity") == "restaurant" and "cuisine" not in tags:
                suggestions.append("Consider adding 'cuisine' tag for restaurants")

            if "opening_hours" in tags:
                hours = tags["opening_hours"]
                if not any(
                    x in hours
                    for x in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su", "24/7"]
                ):
                    suggestions.append(
                        "Opening hours format may not be standard OSM format"
                    )

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
                "quality_grade": (
                    "A"
                    if score >= 90
                    else "B" if score >= 70 else "C" if score >= 50 else "D"
                ),
            },
            "message": f"Validation completed with score {score}/100 and grade {('A' if score >= 90 else 'B' if score >= 70 else 'C' if score >= 50 else 'D')}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to validate OSM data",
        }


@_read_tool
async def get_changeset_history(
    user_id: Optional[int] = None, limit: int = 20
) -> Dict[str, Any]:
    """Get changeset history for analysis and tracking.

    Args:
        user_id: Optional user ID to filter changesets
        limit: Maximum number of changesets to return

    Returns:
        Dictionary containing changeset history
    """
    try:
        # Build query URL
        query_params = {"limit": min(limit, 100)}  # API limit
        if user_id:
            query_params["user"] = user_id

        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        url = f"{config.current_api_base_url}/changesets?{query_string}"
        logger.debug(f"Fetching changeset history from {url}")

        async with get_public_client() as client:
            response = await client.get(url)
            response.raise_for_status()

            # Parse XML response
            changesets = []
            try:
                import xml.etree.ElementTree as ET

                root = parse_xml(response.text)

                for changeset in root.findall(".//changeset"):
                    changeset_data: Dict[str, Any] = {
                        "id": int(changeset.get("id", 0)),
                        "created_at": changeset.get("created_at"),
                        "closed_at": changeset.get("closed_at"),
                        "open": changeset.get("open") == "true",
                        "user": changeset.get("user"),
                        "uid": changeset.get("uid"),
                        "changes_count": int(changeset.get("changes_count", 0)),
                        "tags": {},
                    }

                    # Extract tags
                    for tag in changeset.findall(".//tag"):
                        key = tag.get("k")
                        value = tag.get("v")
                        if key and value:
                            changeset_data["tags"][key] = value

                    changesets.append(changeset_data)

            except Exception as parse_error:
                return {
                    "success": False,
                    "error": f"Failed to parse changeset data: {str(parse_error)}",
                    "raw_response": response.text[:500],
                }

        return {
            "success": True,
            "data": {
                "changesets": changesets,
                "total_count": len(changesets),
                "query_params": query_params,
            },
            "message": f"Retrieved {len(changesets)} changesets",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to get changeset history",
        }


@_read_tool
async def export_osm_data(
    bbox: str, format: str = "json", include_metadata: bool = True
) -> Dict[str, Any]:
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
        if not area_result["success"]:
            return area_result

        elements = area_result["data"]["elements"]

        if format.lower() == "geojson":
            # Convert to GeoJSON format
            features = []
            for element in elements:
                if "lat" in element and "lon" in element:
                    feature: Dict[str, Any] = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [element["lon"], element["lat"]],
                        },
                        "properties": {
                            "id": element["id"],
                            "type": element["type"],
                            "tags": element.get("tags", {}),
                        },
                    }

                    if include_metadata:
                        feature["properties"]["version"] = element.get("version")
                        feature["properties"]["changeset"] = element.get("changeset")
                        feature["properties"]["timestamp"] = element.get("timestamp")
                        feature["properties"]["user"] = element.get("user")

                    features.append(feature)

            exported_data: Any = {"type": "FeatureCollection", "features": features}

        elif format.lower() == "xml":
            # Convert to OSM XML format
            xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml_lines.append('<osm version="0.6" generator="OSM-Edit-MCP">')

            for element in elements:
                if element["type"] == "node":
                    xml_lines.append(
                        f'  <node id="{int(element["id"])}" lat="{element.get("lat", 0)}" lon="{element.get("lon", 0)}">'
                    )
                    xml_lines.append(f'    {build_tags_xml(element.get("tags", {}))}')
                    xml_lines.append("  </node>")

            xml_lines.append("</osm>")
            exported_data = "\n".join(xml_lines)

        else:  # Default to JSON
            exported_data = {
                "elements": elements,
                "bbox": bbox,
                "export_timestamp": "2024-01-01T00:00:00Z",  # Would be current timestamp
                "total_elements": len(elements),
            }

            if not include_metadata:
                # Remove metadata fields
                for element in exported_data["elements"]:
                    for field in ["version", "changeset", "timestamp", "user"]:
                        element.pop(field, None)

        return {
            "success": True,
            "data": {
                "exported_data": exported_data,
                "format": format,
                "bbox": bbox,
                "element_count": len(elements),
                "include_metadata": include_metadata,
            },
            "message": f"Exported {len(elements)} elements in {format} format",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to export OSM data",
        }


@_read_tool
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
        if not area_result["success"]:
            return area_result

        elements = area_result["data"]["elements"]

        # Calculate statistics
        stats: Dict[str, Any] = {
            "total_elements": len(elements),
            "element_types": {},
            "amenity_breakdown": {},
            "shop_breakdown": {},
            "tourism_breakdown": {},
            "tag_frequency": {},
            "completeness_score": 0,
            "data_quality": {},
        }

        # Count element types
        for element in elements:
            element_type = element["type"]
            stats["element_types"][element_type] = (
                stats["element_types"].get(element_type, 0) + 1
            )

        # Analyze tags
        all_tags: Dict[str, Dict[str, int]] = {}
        for element in elements:
            tags = element.get("tags", {})

            # Count tag frequency
            for key, value in tags.items():
                if key not in all_tags:
                    all_tags[key] = {}
                all_tags[key][value] = all_tags[key].get(value, 0) + 1

            # Categorize by major tags
            if "amenity" in tags:
                amenity = tags["amenity"]
                stats["amenity_breakdown"][amenity] = (
                    stats["amenity_breakdown"].get(amenity, 0) + 1
                )

            if "shop" in tags:
                shop = tags["shop"]
                stats["shop_breakdown"][shop] = stats["shop_breakdown"].get(shop, 0) + 1

            if "tourism" in tags:
                tourism = tags["tourism"]
                stats["tourism_breakdown"][tourism] = (
                    stats["tourism_breakdown"].get(tourism, 0) + 1
                )

        # Calculate top tags
        stats["tag_frequency"] = {key: len(values) for key, values in all_tags.items()}

        # Sort by frequency (top 10)
        stats["tag_frequency"] = dict(
            sorted(stats["tag_frequency"].items(), key=lambda x: x[1], reverse=True)[
                :10
            ]
        )

        # Calculate completeness score
        elements_with_names = sum(
            1 for el in elements if el.get("tags", {}).get("name")
        )
        elements_with_types = sum(
            1
            for el in elements
            if any(
                key in el.get("tags", {})
                for key in ["amenity", "shop", "tourism", "leisure"]
            )
        )

        if elements:
            stats["completeness_score"] = {
                "name_coverage": round((elements_with_names / len(elements)) * 100, 1),
                "type_coverage": round((elements_with_types / len(elements)) * 100, 1),
                "overall_score": round(
                    ((elements_with_names + elements_with_types) / (len(elements) * 2))
                    * 100,
                    1,
                ),
            }

        # Data quality assessment
        stats["data_quality"] = {
            "elements_with_coordinates": sum(
                1 for el in elements if "lat" in el and "lon" in el
            ),
            "elements_with_tags": sum(1 for el in elements if el.get("tags")),
            "potential_duplicates": 0,  # Would need more complex logic
            "missing_names": len(elements) - elements_with_names,
            "missing_types": len(elements) - elements_with_types,
        }

        return {
            "success": True,
            "data": stats,
            "message": f"Generated statistics for {len(elements)} elements in the specified area",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to generate OSM statistics",
        }


@_read_tool
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
        if (
            place_result["success"]
            and place_result["data"]
            and place_result["data"].get("places")
        ):
            for place in place_result["data"]["places"][:3]:  # Top 3 results
                # get_place_info nests coordinates under a 'coordinates' key
                coordinates = place.get("coordinates", {})
                results.append(
                    {
                        "source": "nominatim",
                        "confidence": place.get("importance", 0.5),
                        "lat": coordinates.get("lat"),
                        "lon": coordinates.get("lon"),
                        "display_name": place.get("display_name"),
                        "address": place.get("address", {}),
                        "type": place.get("type"),
                        "class": place.get("class"),
                    }
                )

        # Strategy 2: Parse address components
        address_components = parse_address_components(address_or_description)

        # Address-only geocoding has no reliable bounded Overpass scope.
        # Never silently run a global fallback or turn a scope error into zero matches.
        overpass_fallback = (
            "Not attempted: use search_osm_elements with bbox or lat/lon/radius_meters"
        )

        # Rank results by confidence
        results = sorted(results, key=lambda x: x["confidence"], reverse=True)

        return {
            "success": True,
            "data": {
                "query": address_or_description,
                "results": results,
                "best_match": results[0] if results else None,
                "total_candidates": len(results),
                "address_components": address_components,
                "overpass_fallback": overpass_fallback,
            },
            "message": f"Found {len(results)} geocoding candidates for '{address_or_description}'",
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to geocode address",
        }
