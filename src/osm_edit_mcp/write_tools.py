"""OSM mutation tools and higher-level write workflows."""

from typing import Any, Dict, List, Optional

from defusedxml.ElementTree import fromstring as parse_xml

from .app import mcp
from .config import config, logger
from .http_client import describe_exception, get_authenticated_client
from .natural_language import (
    map_business_type_to_tags,
    map_features_to_tags,
    parse_natural_language_request,
)
from .read_tools import get_place_info, search_osm_elements
from .token_store import load_oauth_token
from .xml_models import build_tags_xml

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
        # Check authentication
        token_data = load_oauth_token()
        if not token_data:
            return {
                "success": False,
                "error": "No authentication token",
                "message": "Changeset creation requires OAuth authentication. Run 'python oauth_auth.py' to authenticate."
            }

        changeset_tags = {
            "comment": comment,
            "created_by": config.default_changeset_created_by,
            "source": config.default_changeset_source
        }
        if tags:
            changeset_tags.update(tags)

        # Create changeset XML
        changeset_xml = f"<osm><changeset>{build_tags_xml(changeset_tags)}</changeset></osm>"

        url = f"{config.current_api_base_url}/changeset/create"
        logger.debug(f"Creating changeset at {url}")
        async with get_authenticated_client() as client:
            response = await client.put(
                url,
                content=changeset_xml,
                headers={"Content-Type": "text/xml"}
            )

            if response.status_code == 200:
                changeset_id = int(response.text.strip())
                logger.info(f"Created changeset {changeset_id} by user {token_data.get('username', 'unknown')}")

                return {
                    "success": True,
                    "data": {
                        "changeset_id": changeset_id,
                        "tags": changeset_tags,
                        "created_by": token_data.get('username', 'unknown'),
                        "api_url": f"{config.current_api_base_url}/changeset/{changeset_id}"
                    },
                    "message": f"Created changeset {changeset_id}"
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}",
                    "message": f"Failed to create changeset: {response.text}"
                }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to create changeset"
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
        # Check authentication
        token_data = load_oauth_token()
        if not token_data:
            return {
                "success": False,
                "error": "No authentication token",
                "message": "Changeset closing requires OAuth authentication. Run 'python oauth_auth.py' to authenticate."
            }

        url = f"{config.current_api_base_url}/changeset/{changeset_id}/close"
        logger.debug(f"Closing changeset {changeset_id} at {url}")
        async with get_authenticated_client() as client:
            response = await client.put(url)

            if response.status_code == 200:
                logger.info(f"Closed changeset {changeset_id} by user {token_data.get('username', 'unknown')}")
                return {
                    "success": True,
                    "data": {
                        "changeset_id": changeset_id,
                        "closed_by": token_data.get('username', 'unknown'),
                        "api_url": f"{config.current_api_base_url}/changeset/{changeset_id}"
                    },
                    "message": f"Closed changeset {changeset_id}"
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}",
                    "message": f"Failed to close changeset {changeset_id}: {response.text}"
                }
    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to close changeset {changeset_id}"
        }


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
        node_xml = (
            f'<osm><node changeset="{int(changeset_id)}" lat="{lat}" lon="{lon}">'
            f'{build_tags_xml(tags)}</node></osm>'
        )

        # Check authentication
        token_data = load_oauth_token()
        if not token_data:
            return {
                "success": False,
                "error": "Authentication required",
                "message": "Node creation requires OAuth authentication. Run 'python oauth_auth.py' to authenticate."
            }

        # Create node via OSM API
        url = f"{config.current_api_base_url}/node/create"
        async with get_authenticated_client() as client:
            response = await client.put(url, content=node_xml, headers={"Content-Type": "text/xml"})

            if response.status_code == 200:
                node_id = int(response.text.strip())
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "coordinates": {"lat": lat, "lon": lon},
                        "tags": tags,
                        "changeset_id": changeset_id
                    },
                    "message": f"Created node {node_id} successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}",
                    "message": f"Failed to create node: {response.text}"
                }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to create node"
        }

# OSM Tag Mapping System for Natural Language Processing

# The functions below build the correct request payloads but never send them -
# they return a "would_create"/"would_update"/"would_delete" preview instead.
# They are deliberately NOT registered as MCP tools (no @mcp.tool()): exposing
# them would advertise capabilities to an agent that the server cannot deliver,
# producing confusing failures mid-edit. Add the decorator back once the OSM API
# calls (including version fetch and conflict handling) are actually wired up.
#
# Implemented and registered write tools: create_changeset, close_changeset,
# create_osm_node, update_osm_node.
# ---------------------------------------------------------------------------

async def create_osm_way(node_ids: List[int], tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Create a new OSM way from a list of node IDs (requires authentication).

    Args:
        node_ids: List of node IDs that form the way
        tags: Dictionary of tags for the way
        changeset_id: ID of the changeset to add this way to

    Returns:
        Dictionary containing the new way ID and status
    """
    try:
        # Validate node IDs
        if not node_ids or len(node_ids) < 2:
            return {
                "success": False,
                "error": "Invalid node list",
                "message": "A way must contain at least 2 nodes"
            }

        # Create way XML
        nds_xml = "".join(f'<nd ref="{int(node_id)}"/>' for node_id in node_ids)
        way_xml = (
            f'<osm><way changeset="{int(changeset_id)}">'
            f'{nds_xml}{build_tags_xml(tags)}</way></osm>'
        )

        # Note: This would require OAuth authentication for actual creation
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Way creation requires OAuth authentication. This is a read-only demo.",
            "would_create": {
                "node_ids": node_ids,
                "tags": tags,
                "changeset_id": changeset_id,
                "xml": way_xml
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to create way"
        }

async def create_osm_relation(members: List[Dict[str, Any]], tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Create a new OSM relation from a list of members (requires authentication).

    Args:
        members: List of relation members with type, ref, and role
        tags: Dictionary of tags for the relation
        changeset_id: ID of the changeset to add this relation to

    Returns:
        Dictionary containing the new relation ID and status
    """
    try:
        # Validate members
        if not members:
            return {
                "success": False,
                "error": "Invalid member list",
                "message": "A relation must contain at least one member"
            }

        # Create relation XML
        members_xml = ""
        for member in members:
            member_type = member.get('type', 'node')
            member_ref = member.get('ref', 0)
            member_role = member.get('role', '')
            members_xml += (
                f'<member type={quoteattr(str(member_type))} ref="{int(member_ref)}" '
                f'role={quoteattr(str(member_role))}/>'
            )

        relation_xml = (
            f'<osm><relation changeset="{int(changeset_id)}">'
            f'{members_xml}{build_tags_xml(tags)}</relation></osm>'
        )

        # Note: This would require OAuth authentication for actual creation
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Relation creation requires OAuth authentication. This is a read-only demo.",
            "would_create": {
                "members": members,
                "tags": tags,
                "changeset_id": changeset_id,
                "xml": relation_xml
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to create relation"
        }

@mcp.tool()
async def update_osm_node(node_id: int, lat: float, lon: float, tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Update an existing OSM node (requires authentication).

    Args:
        node_id: ID of the node to update
        lat: New latitude coordinate
        lon: New longitude coordinate
        tags: Dictionary of tags for the node
        changeset_id: ID of the changeset for this update

    Returns:
        Dictionary containing update status
    """
    try:
        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {
                "success": False,
                "error": "Invalid coordinates",
                "message": "Latitude must be between -90 and 90, longitude between -180 and 180"
            }

        # Check authentication
        token_data = load_oauth_token()
        if not token_data:
            return {
                "success": False,
                "error": "Authentication required",
                "message": "Node update requires OAuth authentication. Run 'python oauth_auth.py' to authenticate."
            }

        # First, get the current node to retrieve version
        url = f"{config.current_api_base_url}/node/{node_id}"
        async with get_authenticated_client() as client:
            get_response = await client.get(url)

            if get_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get node: {get_response.status_code}",
                    "message": f"Could not retrieve node {node_id}: {get_response.text}"
                }

            # Parse version from XML response
            root = parse_xml(get_response.text)
            node_elem = root.find('.//node')
            version = node_elem.get('version') if node_elem is not None else None
            if version is None:
                return {
                    "success": False,
                    "error": "Missing version",
                    "message": (
                        f"Could not determine the current version of node {node_id}; "
                        "refusing to update without it, as that would risk overwriting "
                        "another mapper's edit."
                    )
                }

            # Create node XML for update
            node_xml = (
                f'<osm><node id="{int(node_id)}" changeset="{int(changeset_id)}" '
                f'version="{int(version)}" lat="{lat}" lon="{lon}">'
                f'{build_tags_xml(tags)}</node></osm>'
            )

            # Update node via OSM API
            update_url = f"{config.current_api_base_url}/node/{node_id}"
            update_response = await client.put(update_url, content=node_xml, headers={"Content-Type": "text/xml"})

            if update_response.status_code == 200:
                new_version = int(update_response.text.strip())
                return {
                    "success": True,
                    "data": {
                        "node_id": node_id,
                        "version": new_version,
                        "coordinates": {"lat": lat, "lon": lon},
                        "tags": tags,
                        "changeset_id": changeset_id
                    },
                    "message": f"Updated node {node_id} to version {new_version}"
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {update_response.status_code}",
                    "message": f"Failed to update node: {update_response.text}"
                }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to update node {node_id}"
        }

async def update_osm_way(way_id: int, node_ids: List[int], tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Update an existing OSM way (requires authentication).

    Args:
        way_id: ID of the way to update
        node_ids: List of node IDs that form the way
        tags: Dictionary of tags for the way
        changeset_id: ID of the changeset for this update

    Returns:
        Dictionary containing update status
    """
    try:
        # Validate node IDs
        if not node_ids or len(node_ids) < 2:
            return {
                "success": False,
                "error": "Invalid node list",
                "message": "A way must contain at least 2 nodes"
            }

        # Note: This would require OAuth authentication and version info
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Way update requires OAuth authentication. This is a read-only demo.",
            "would_update": {
                "way_id": way_id,
                "node_ids": node_ids,
                "tags": tags,
                "changeset_id": changeset_id
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to update way {way_id}"
        }

async def update_osm_relation(relation_id: int, members: List[Dict[str, Any]], tags: Dict[str, str], changeset_id: int) -> Dict[str, Any]:
    """Update an existing OSM relation (requires authentication).

    Args:
        relation_id: ID of the relation to update
        members: List of relation members with type, ref, and role
        tags: Dictionary of tags for the relation
        changeset_id: ID of the changeset for this update

    Returns:
        Dictionary containing update status
    """
    try:
        # Validate members
        if not members:
            return {
                "success": False,
                "error": "Invalid member list",
                "message": "A relation must contain at least one member"
            }

        # Note: This would require OAuth authentication and version info
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Relation update requires OAuth authentication. This is a read-only demo.",
            "would_update": {
                "relation_id": relation_id,
                "members": members,
                "tags": tags,
                "changeset_id": changeset_id
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to update relation {relation_id}"
        }

async def delete_osm_node(node_id: int, changeset_id: int) -> Dict[str, Any]:
    """Delete an existing OSM node (requires authentication and confirmation).

    Args:
        node_id: ID of the node to delete
        changeset_id: ID of the changeset for this deletion

    Returns:
        Dictionary containing deletion status
    """
    try:
        # Note: This would require OAuth authentication and version info
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Node deletion requires OAuth authentication and user confirmation. This is a read-only demo.",
            "would_delete": {
                "node_id": node_id,
                "changeset_id": changeset_id,
                "warning": "This is a destructive operation that cannot be undone easily"
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to delete node {node_id}"
        }

async def delete_osm_way(way_id: int, changeset_id: int) -> Dict[str, Any]:
    """Delete an existing OSM way (requires authentication and confirmation).

    Args:
        way_id: ID of the way to delete
        changeset_id: ID of the changeset for this deletion

    Returns:
        Dictionary containing deletion status
    """
    try:
        # Note: This would require OAuth authentication and version info
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Way deletion requires OAuth authentication and user confirmation. This is a read-only demo.",
            "would_delete": {
                "way_id": way_id,
                "changeset_id": changeset_id,
                "warning": "This is a destructive operation that cannot be undone easily"
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to delete way {way_id}"
        }

async def delete_osm_relation(relation_id: int, changeset_id: int) -> Dict[str, Any]:
    """Delete an existing OSM relation (requires authentication and confirmation).

    Args:
        relation_id: ID of the relation to delete
        changeset_id: ID of the changeset for this deletion

    Returns:
        Dictionary containing deletion status
    """
    try:
        # Note: This would require OAuth authentication and version info
        return {
            "success": False,
            "error": "Authentication required",
            "message": "Relation deletion requires OAuth authentication and user confirmation. This is a read-only demo.",
            "would_delete": {
                "relation_id": relation_id,
                "changeset_id": changeset_id,
                "warning": "This is a destructive operation that cannot be undone easily"
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": f"Failed to delete relation {relation_id}"
        }

# High-Level Natural Language Tools

@mcp.tool()
async def create_place_from_description(description: str, changeset_id: Optional[int] = None) -> Dict[str, Any]:
    """Create a new place on OSM from a natural language description.

    Args:
        description: Natural language description of the place to create
        changeset_id: Optional changeset ID (will create one if not provided)

    Returns:
        Dictionary containing the parsed request and creation plan
    """
    try:
        # Parse the natural language request
        parsed = parse_natural_language_request(description)

        if parsed['action'] not in ['create']:
            return {
                "success": False,
                "error": "Invalid action",
                "message": f"This tool is for creating places. Detected action: {parsed['action']}"
            }

        # Build OSM tags from parsed data
        tags = {}

        # Add name if specified
        if parsed['name']:
            tags['name'] = parsed['name']

        # Add business type tags
        if parsed['business_type']:
            business_tags = map_business_type_to_tags(parsed['business_type'])
            tags.update(business_tags)

        # Add feature tags
        if parsed['features']:
            feature_tags = map_features_to_tags(parsed['features'])
            tags.update(feature_tags)

        # Determine coordinates
        coordinates = parsed['coordinates']
        if not coordinates and parsed['address']:
            # Try to resolve address to coordinates
            place_info = await get_place_info(parsed['address'])
            if place_info['success'] and place_info['data']['places']:
                first_place = place_info['data']['places'][0]
                coordinates = first_place['coordinates']

        if not coordinates:
            return {
                "success": False,
                "error": "No coordinates found",
                "message": "Could not determine coordinates from the description. Please provide coordinates or a specific address."
            }

        # Create changeset if not provided
        if not changeset_id:
            changeset_result: Dict[str, Any] = await create_changeset(
                comment=f"Created place: {parsed['name'] or parsed['business_type']} via MCP",
                tags={"created_by": "OSM-Edit-MCP", "source": "natural_language"}
            )
            if not changeset_result['success']:
                return changeset_result
            changeset_id = changeset_result['data']['changeset_id']

        # Create the node
        node_result = await create_osm_node(
            lat=coordinates['lat'],
            lon=coordinates['lon'],
            tags=tags,
            changeset_id=changeset_id
        )

        return {
            "success": True,
            "data": {
                "parsed_request": parsed,
                "proposed_tags": tags,
                "coordinates": coordinates,
                "changeset_id": changeset_id,
                "node_creation": node_result
            },
            "message": f"Parsed request to create {parsed['business_type'] or 'place'} with {len(tags)} tags"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to create place from description"
        }

@mcp.tool()
async def find_and_update_place(description: str, changeset_id: Optional[int] = None) -> Dict[str, Any]:
    """Find and update a place on OSM from a natural language description.

    Args:
        description: Natural language description of what to find and how to update it
        changeset_id: Optional changeset ID (will create one if not provided)

    Returns:
        Dictionary containing the search results and update plan
    """
    try:
        # Parse the natural language request
        parsed = parse_natural_language_request(description)

        if parsed['action'] not in ['update']:
            return {
                "success": False,
                "error": "Invalid action",
                "message": f"This tool is for updating places. Detected action: {parsed['action']}"
            }

        # Search for the place
        search_term = parsed['name'] or parsed['business_type'] or 'place'
        search_result = await search_osm_elements(search_term)

        if not search_result['success'] or not search_result['data']['elements']:
            return {
                "success": False,
                "error": "No places found",
                "message": f"Could not find any places matching: {search_term}"
            }

        # Get the first matching element
        element = search_result['data']['elements'][0]

        # Build new tags from parsed data
        new_tags = element.get('tags', {}).copy()

        # Update name if specified
        if parsed['name']:
            new_tags['name'] = parsed['name']

        # Update business type tags
        if parsed['business_type']:
            business_tags = map_business_type_to_tags(parsed['business_type'])
            new_tags.update(business_tags)

        # Update feature tags
        if parsed['features']:
            feature_tags = map_features_to_tags(parsed['features'])
            new_tags.update(feature_tags)

        # Create changeset if not provided
        if not changeset_id:
            changeset_result: Dict[str, Any] = await create_changeset(
                comment=f"Updated place: {element.get('tags', {}).get('name', 'unnamed')} via MCP",
                tags={"created_by": "OSM-Edit-MCP", "source": "natural_language"}
            )
            if not changeset_result['success']:
                return changeset_result
            changeset_id = changeset_result['data']['changeset_id']

        # Update based on element type
        if element['type'] == 'node':
            update_result = await update_osm_node(
                node_id=element['id'],
                lat=element.get('location', {}).get('lat', 0),
                lon=element.get('location', {}).get('lon', 0),
                tags=new_tags,
                changeset_id=changeset_id
            )
        elif element['type'] == 'way':
            # For ways, we'd need to get the current node list first
            update_result = {
                "success": False,
                "error": "Way update not implemented",
                "message": "Way updates require fetching current node list first"
            }
        else:
            update_result = {
                "success": False,
                "error": "Unsupported element type",
                "message": f"Cannot update {element['type']} elements yet"
            }

        return {
            "success": True,
            "data": {
                "parsed_request": parsed,
                "found_element": element,
                "proposed_tags": new_tags,
                "changeset_id": changeset_id,
                "update_result": update_result
            },
            "message": f"Found and prepared update for {element['type']} {element['id']}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to find and update place"
        }

@mcp.tool()
async def delete_place_from_description(description: str, changeset_id: Optional[int] = None) -> Dict[str, Any]:
    """Delete a place on OSM from a natural language description (requires confirmation).

    Args:
        description: Natural language description of what to delete
        changeset_id: Optional changeset ID (will create one if not provided)

    Returns:
        Dictionary containing the search results and deletion plan
    """
    try:
        # Parse the natural language request
        parsed = parse_natural_language_request(description)

        if parsed['action'] not in ['delete']:
            return {
                "success": False,
                "error": "Invalid action",
                "message": f"This tool is for deleting places. Detected action: {parsed['action']}"
            }

        # Search for the place
        search_term = parsed['name'] or parsed['business_type'] or 'place'
        search_result = await search_osm_elements(search_term)

        if not search_result['success'] or not search_result['data']['elements']:
            return {
                "success": False,
                "error": "No places found",
                "message": f"Could not find any places matching: {search_term}"
            }

        # Get the first matching element
        element = search_result['data']['elements'][0]

        # Create changeset if not provided
        if not changeset_id:
            changeset_result: Dict[str, Any] = await create_changeset(
                comment=f"Deleted place: {element.get('tags', {}).get('name', 'unnamed')} via MCP",
                tags={"created_by": "OSM-Edit-MCP", "source": "natural_language"}
            )
            if not changeset_result['success']:
                return changeset_result
            changeset_id = changeset_result['data']['changeset_id']

        # Delete based on element type
        if element['type'] == 'node':
            delete_result = await delete_osm_node(
                node_id=element['id'],
                changeset_id=changeset_id
            )
        elif element['type'] == 'way':
            delete_result = await delete_osm_way(
                way_id=element['id'],
                changeset_id=changeset_id
            )
        elif element['type'] == 'relation':
            delete_result = await delete_osm_relation(
                relation_id=element['id'],
                changeset_id=changeset_id
            )
        else:
            delete_result = {
                "success": False,
                "error": "Unsupported element type",
                "message": f"Cannot delete {element['type']} elements"
            }

        return {
            "success": True,
            "data": {
                "parsed_request": parsed,
                "found_element": element,
                "changeset_id": changeset_id,
                "delete_result": delete_result,
                "warning": "DESTRUCTIVE OPERATION - This will permanently remove the element from OSM"
            },
            "message": f"Found and prepared deletion for {element['type']} {element['id']}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to find and delete place"
        }


@mcp.tool()
async def bulk_create_places(places_data: List[Dict[str, Any]], changeset_id: Optional[int] = None) -> Dict[str, Any]:
    """Create multiple places at once from structured data.

    Args:
        places_data: List of place dictionaries with keys: name, type, lat, lon, features
        changeset_id: Optional changeset ID (will create one if not provided)

    Returns:
        Dictionary containing results of bulk creation
    """
    try:
        if not places_data:
            return {
                "success": False,
                "error": "No places data provided",
                "message": "Please provide a list of places to create"
            }

        # Create changeset if not provided
        if not changeset_id:
            changeset_result: Dict[str, Any] = await create_changeset(
                comment=f"Bulk created {len(places_data)} places via MCP",
                tags={"created_by": "OSM-Edit-MCP", "source": "bulk_operation"}
            )
            if not changeset_result['success']:
                return changeset_result
            changeset_id = changeset_result['data']['changeset_id']

        results = []
        success_count = 0

        for i, place_data in enumerate(places_data):
            try:
                # Extract place information
                name = place_data.get('name', f'Place {i+1}')
                place_type = place_data.get('type', 'place')
                lat = place_data.get('lat', 0)
                lon = place_data.get('lon', 0)
                features = place_data.get('features', [])

                # Generate tags
                tags = {'name': name}

                # Add business type tags
                business_tags = map_business_type_to_tags(place_type)
                tags.update(business_tags)

                # Add feature tags
                if features:
                    feature_tags = map_features_to_tags(features)
                    tags.update(feature_tags)

                # Create the node
                create_result = await create_osm_node(
                    lat=lat,
                    lon=lon,
                    tags=tags,
                    changeset_id=changeset_id
                )

                if create_result['success']:
                    success_count += 1

                results.append({
                    'place_data': place_data,
                    'result': create_result,
                    'index': i
                })

            except Exception as e:
                results.append({
                    'place_data': place_data,
                    'result': {'success': False, 'error': str(e)},
                    'index': i
                })

        return {
            "success": True,
            "data": {
                "changeset_id": changeset_id,
                "total_places": len(places_data),
                "successful_creates": success_count,
                "failed_creates": len(places_data) - success_count,
                "results": results
            },
            "message": f"Bulk creation completed: {success_count}/{len(places_data)} places created successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "error": describe_exception(e),
            "message": "Failed to bulk create places"
        }
