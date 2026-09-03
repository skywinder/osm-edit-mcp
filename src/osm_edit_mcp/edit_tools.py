"""Safe discovery, capability and audit tools for the edit workflow."""

from typing import Any, Dict, List, Optional

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations

from .app import mcp
from .auth import verify_write_identity
from .config import config
from .http_client import (
    describe_exception,
    get_authenticated_client,
    get_public_client,
)
from .track_tools import _PROPOSAL_STORE, _verify_diff_results
from .valhalla import status as valhalla_status

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lon, min_lat, max_lon, max_lat = [
            float(value.strip()) for value in bbox.split(",")
        ]
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox must be min_lon,min_lat,max_lon,max_lat") from exc
    if not (-180 <= min_lon < max_lon <= 180):
        raise ValueError("bbox longitude range is invalid")
    if not (-90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox latitude range is invalid")
    if (max_lon - min_lon) * (max_lat - min_lat) > 0.25:
        raise ValueError("bbox is too large for the OSM map API")
    return min_lon, min_lat, max_lon, max_lat


def _tags(element: Any) -> Dict[str, str]:
    return {
        child.get("k", ""): child.get("v", "")
        for child in element.findall("tag")
        if child.get("k")
    }


@mcp.tool(annotations=READ_ONLY)
async def get_edit_capabilities() -> Dict[str, Any]:
    """Describe the active safety profile and optional local services."""
    try:
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
        authentication = {
            "status": "verified",
            "user_id": identity["user_id"],
            "username": identity["username"],
            "permissions": identity["permissions"],
        }
    except Exception as exc:
        authentication = {
            "status": "unavailable",
            "error": describe_exception(exc),
        }
    return {
        "success": True,
        "data": {
            "environment": config.api_environment,
            "api_target": config.current_api_base_url,
            "web_target": config.current_web_base_url,
            "write_profile": config.osm_write_profile,
            "authentication": authentication,
            "production_confirmation": {
                "required": True,
                "mechanism": "MCP elicitation bound to proposal SHA-256",
            },
            "safe_write_tools": [
                "preview_track_road_edit",
                "apply_osm_edit",
            ],
            "track_tools": [
                "analyze_gpx_track",
                "create_track_selection",
                "match_track_selection",
                "suggest_track_road_candidates",
            ],
            "raw_write_tools_registered": config.direct_write_tools_enabled,
            "limits": {
                "gpx_bytes": config.osm_track_max_file_bytes,
                "gpx_raw_points": config.osm_track_max_points,
                "proposal_ttl_seconds": config.osm_track_proposal_ttl_seconds,
                "local_changeset_elements": config.max_changeset_size,
            },
            "valhalla": await valhalla_status(),
        },
    }


@mcp.tool(annotations=READ_ONLY)
async def inspect_map_context(
    bbox: str,
    highway_only: bool = False,
    max_elements: int = 5_000,
) -> Dict[str, Any]:
    """Return stable OSM IDs, versions, tags and GeoJSON for a small bbox."""
    try:
        min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox)
        if not 1 <= max_elements <= 10_000:
            raise ValueError("max_elements must be between 1 and 10000")
        normalized = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        async with get_public_client() as client:
            response = await client.get(
                f"{config.current_api_base_url}/map", params={"bbox": normalized}
            )
        response.raise_for_status()
        root = parse_xml(response.text)
        nodes: Dict[int, Dict[str, Any]] = {}
        for element in root.findall("node"):
            node_id = int(element.get("id", "0"))
            nodes[node_id] = {
                "id": node_id,
                "version": int(element.get("version", "0")),
                "lat": float(element.get("lat", "0")),
                "lon": float(element.get("lon", "0")),
                "tags": _tags(element),
            }
        elements: List[Dict[str, Any]] = []
        features: List[Dict[str, Any]] = []
        for element in root.findall("way"):
            tags = _tags(element)
            if highway_only and "highway" not in tags:
                continue
            way_id = int(element.get("id", "0"))
            refs = [int(nd.get("ref", "0")) for nd in element.findall("nd")]
            coordinates = [
                [nodes[ref]["lon"], nodes[ref]["lat"]] for ref in refs if ref in nodes
            ]
            record = {
                "type": "way",
                "id": way_id,
                "version": int(element.get("version", "0")),
                "node_ids": refs,
                "tags": tags,
            }
            elements.append(record)
            if len(coordinates) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "osm_type": "way",
                            "osm_id": way_id,
                            "version": record["version"],
                            **tags,
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coordinates,
                        },
                    }
                )
        if not highway_only:
            for node in nodes.values():
                if not node["tags"]:
                    continue
                elements.append(
                    {
                        "type": "node",
                        "id": node["id"],
                        "version": node["version"],
                        "tags": node["tags"],
                    }
                )
        if len(elements) > max_elements:
            raise ValueError(
                f"Area contains {len(elements)} selected elements; narrow the bbox"
            )
        return {
            "success": True,
            "data": {
                "bbox": normalized,
                "elements": elements,
                "geojson": {"type": "FeatureCollection", "features": features},
                "node_count": len(nodes),
                "selected_element_count": len(elements),
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "error": type(exc).__name__,
            "message": "Failed to inspect the requested map area",
            "detail": describe_exception(exc),
        }


@mcp.tool(annotations=READ_ONLY)
async def list_edit_proposals(
    status: Optional[str] = None, limit: int = 20
) -> Dict[str, Any]:
    """List local proposal metadata without exposing raw GPX coordinates."""
    proposals = _PROPOSAL_STORE.list(status=status, limit=limit)
    return {
        "success": True,
        "data": [
            {
                "proposal_id": proposal.proposal_id,
                "status": proposal.status,
                "proposal_digest": proposal.digest,
                "created_at_unix": proposal.created_at,
                "expires_at_unix": proposal.expires_at,
                "api_target": proposal.api_target,
                "osm_uid": proposal.osm_uid,
                "changeset_id": proposal.changeset_id,
                "action": proposal.payload.get("action"),
                "summary": proposal.payload.get("summary"),
                "preview_uri": f"ui://osm-edit/proposal/{proposal.proposal_id}",
            }
            for proposal in proposals
        ],
    }


@mcp.tool(annotations=READ_ONLY)
async def verify_osm_edit(proposal_id: str) -> Dict[str, Any]:
    """Re-fetch every element recorded in an applied proposal receipt."""
    proposal = _PROPOSAL_STORE.get(proposal_id, include_expired=True)
    if proposal is None:
        return {"success": False, "error": "Unknown proposal"}
    if proposal.status != "APPLIED" or not proposal.receipt:
        return {
            "success": False,
            "error": "Proposal is not applied",
            "status": proposal.status,
        }
    async with get_public_client() as client:
        verification = await _verify_diff_results(
            client, proposal.receipt.get("diff_results", [])
        )
    return {
        "success": verification["status"] == "verified",
        "data": {
            "proposal_id": proposal_id,
            "changeset_url": proposal.receipt.get("changeset_url"),
            "verification": verification,
        },
    }


__all__ = [
    "get_edit_capabilities",
    "inspect_map_context",
    "list_edit_proposals",
    "verify_osm_edit",
]
