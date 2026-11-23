"""Review an observed, one-direction bus itinerary against the current OSM map."""

import asyncio
import html
import json
from typing import Annotated, Any, Literal

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from . import track_tools
from .app import profile_tool
from .auth import verify_write_identity
from .config import config
from .discovery_models import Latitude, Longitude
from .http_client import describe_exception, get_authenticated_client, get_public_client
from .place_features import ATTRIBUTION
from .transit_apply import conflicting_bus_routes, read_route_parents
from .transit_data import (
    element_tags,
    fetch_route_objects,
    restriction_snapshot,
    restriction_via_ways,
    turn_issues,
)
from .transit_geometry import match_stop_candidates, validate_route_geometry
from .transit_update import (
    BoardingRole,
    preserve_boarding_roles,
    read_bus_direction,
    route_changes,
)

ObjectId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Label = Annotated[str, Field(min_length=1, max_length=255)]
SourceBasis = Literal[
    "survey", "local_knowledge", "compatible_license", "permission", "unconfirmed"
]
RouteTag = Literal["ref", "from", "to", "name", "operator", "network"]
READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


class SurveyStop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: Latitude
    lon: Longitude
    label: Label | None = None


class OmittedStop(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: Label
    reason: Label
    node_id: ObjectId | None = None


@profile_tool(annotations=READ)
async def find_bus_route_stops(
    locations: Annotated[list[SurveyStop], Field(min_length=1, max_length=150)],
    radius_m: Annotated[int, Field(ge=5, le=200)] = 50,
) -> dict[str, Any]:
    """Find mapped bus platforms and stop positions near ordered survey locations.
    Local names are returned as mapped. Both sides of the street can appear.
    Select IDs after checking the direction; an empty result is a survey gap.
    Only search bounding boxes are sent to the configured editing API.
    """
    try:
        async with get_public_client() as client:

            async def find(point: SurveyStop) -> dict[str, Any]:
                south, west, north, east = track_tools._expanded_bbox(
                    [(point.lat, point.lon)], radius_m * 1.02
                )
                if south < -90 or north > 90 or west < -180 or east > 180:
                    raise ValueError(
                        "Stop search box crosses a pole or the antimeridian"
                    )
                response = await client.get(
                    f"{config.current_api_base_url}/map",
                    params={"bbox": f"{west},{south},{east},{north}"},
                )
                response.raise_for_status()
                root = parse_xml(response.text)
                if root.tag != "osm":
                    raise ValueError("Expected a complete OSM map response")
                nodes = [
                    {
                        "id": int(n.attrib["id"]),
                        "tags": element_tags(n),
                        "lat": float(n.attrib["lat"]),
                        "lon": float(n.attrib["lon"]),
                    }
                    for n in root.findall("node")
                    if n.find("tag") is not None and n.get("visible") != "false"
                ]
                matches = match_stop_candidates(
                    point.lat, point.lon, nodes, radius_m=radius_m, limit=20
                )
                for item in matches:
                    item["osm_url"] = f"{config.current_web_base_url}/node/{item['id']}"
                return {
                    "location": point.model_dump(exclude_none=True),
                    "candidates": matches,
                    "candidate_limit_reached": len(matches) == 20,
                }

            rows: list[dict[str, Any]] = []
            for offset in range(0, len(locations), 2):
                rows.extend(
                    await asyncio.gather(
                        *(find(p) for p in locations[offset : offset + 2])
                    )
                )
        return {
            "success": True,
            "data": {
                "stops": rows,
                "api_target": config.current_api_base_url,
                "attribution": ATTRIBUTION,
            },
        }
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Could not inspect bus stop candidates",
            detail=describe_exception(exc),
        )


def _text(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 255 or not all(ch.isprintable() for ch in value):
        raise ValueError("OSM text must contain 1–255 printable characters")
    return value


def _geojson(
    path: list[int], stop_ids: list[int], nodes: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    def xy(ref: int) -> list[float]:
        return [nodes[ref]["lon"], nodes[ref]["lat"]]

    features: list[dict[str, Any]] = []
    if path:
        features.append(
            {
                "type": "Feature",
                "properties": {"feature": "bus_path"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [xy(n) for n in path],
                },
            }
        )
    for order, ref in enumerate(stop_ids, 1):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "stop_sequence": order,
                    "name": nodes[ref]["tags"].get("name", ""),
                    "node_id": ref,
                },
                "geometry": {"type": "Point", "coordinates": xy(ref)},
            }
        )
    return {**track_tools._feature_collection(features), "attribution": ATTRIBUTION}


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=True
    )
)
async def preview_bus_route(
    ref: Label,
    from_name: Label,
    to_name: Label,
    way_ids: Annotated[list[ObjectId], Field(min_length=1, max_length=600)],
    stop_ids: Annotated[list[ObjectId], Field(min_length=2, max_length=250)],
    source: Label,
    source_basis: Literal[
        "survey", "local_knowledge", "compatible_license", "permission", "unconfirmed"
    ] = "unconfirmed",
    omitted_stops: Annotated[list[OmittedStop], Field(max_length=150)] | None = None,
    driving_side: Literal["right", "left"] = "right",
    prepare_upload: bool = False,
    name: Label | None = None,
    operator: Label | None = None,
    network: Label | None = None,
) -> dict[str, Any]:
    """Review one PTv2 bus direction using existing way and stop node IDs in travel order.
    Supply surveyed or otherwise OSM-compatible evidence covering the path, direction
    and stops. Record deliberately omitted stops with reasons. Preserve local names.
    A public-data inspection needs no login. Set prepare_upload=true to bind an exact
    eligible proposal to the verified OSM account for apply_osm_edit. The returned
    GeoJSON can also be opened as a custom map data layer in iD.
    """
    try:
        tags = {
            "type": "route",
            "route": "bus",
            "public_transport:version": "2",
            "ref": _text(ref),
            "from": _text(from_name),
            "to": _text(to_name),
        }
        for key, value in (
            ("name", name),
            ("operator", operator),
            ("network", network),
        ):
            if value is not None:
                tags[key] = _text(value)
        return await _review_direction(
            tags,
            way_ids,
            stop_ids,
            source,
            source_basis,
            omitted_stops,
            driving_side,
            prepare_upload,
        )
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Could not prepare the bus route",
            detail=describe_exception(exc),
        )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=True
    )
)
async def preview_bus_route_update(
    relation_id: ObjectId,
    source: Label,
    way_ids: (
        Annotated[list[ObjectId], Field(min_length=1, max_length=600)] | None
    ) = None,
    stop_ids: (
        Annotated[list[ObjectId], Field(min_length=2, max_length=250)] | None
    ) = None,
    boarding_roles: (
        Annotated[list[BoardingRole | None], Field(min_length=2, max_length=250)] | None
    ) = None,
    tag_changes: dict[RouteTag, Label | None] | None = None,
    source_basis: SourceBasis = "unconfirmed",
    omitted_stops: Annotated[list[OmittedStop], Field(max_length=150)] | None = None,
    driving_side: Literal["right", "left"] = "right",
    prepare_upload: bool = False,
) -> dict[str, Any]:
    """Review updates to a mapped PTv2 bus direction, keeping its relation ID and parent memberships.
    Supply replacement stop or road IDs in travel order for the lists you want to change.
    Omitted lists and unrelated tags are preserved. tag_changes can set ref, from, to,
    name, operator or network. Use null to remove an optional tag. Review the before
    snapshot and the exact tag and ordered member changes (zero-based half-open ranges).
    For a relocated restricted stop, supply boarding_roles in stop order with null for
    retained roles and the observed role for the new stop. prepare_upload binds an
    eligible edit to the current relation version and account.
    """
    try:
        async with get_public_client() as client:
            before = await read_bus_direction(client, relation_id)
        tags = dict(before["tags"])
        for key, value in (tag_changes or {}).items():
            if key not in {"ref", "from", "to", "name", "operator", "network"}:
                raise ValueError(f"Unsupported route tag change: {key}")
            if value is None:
                if key in {"ref", "from", "to"}:
                    raise ValueError(f"An explicit change to {key} needs a value")
                tags.pop(key, None)
            else:
                tags[key] = _text(value)
        if way_ids is None:
            way_ids = [m["ref"] for m in before["members"] if m["type"] == "way"]
        if stop_ids is None:
            stop_ids = [m["ref"] for m in before["members"] if m["type"] == "node"]
        return await _review_direction(
            tags,
            way_ids,
            stop_ids,
            source,
            source_basis,
            omitted_stops,
            driving_side,
            prepare_upload,
            before,
            boarding_roles,
        )
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Could not prepare the bus route update",
            detail=describe_exception(exc),
        )


async def _review_direction(
    tags: dict[str, str],
    way_ids: list[int],
    stop_ids: list[int],
    source: str,
    source_basis: SourceBasis,
    omitted_stops: list[OmittedStop] | None,
    driving_side: str,
    prepare_upload: bool,
    before: dict[str, Any] | None = None,
    boarding_roles: list[BoardingRole | None] | None = None,
) -> dict[str, Any]:
    ids = [*way_ids, *stop_ids]
    if not (1 <= len(way_ids) <= 600 and 2 <= len(stop_ids) <= 250) or any(
        type(n) is not int or n <= 0 for n in ids
    ):
        raise ValueError(
            "Supply ordered positive OSM way and stop IDs within the schema limits"
        )
    source = _text(source)
    omitted = [x.model_dump(exclude_none=True) for x in omitted_stops or []]
    if any(row.get("node_id") in stop_ids for row in omitted):
        raise ValueError("A stop ID appears in both the selected and omitted lists")
    async with get_public_client() as client:
        ways, nodes = await fetch_route_objects(client, way_ids, stop_ids)
        try:
            geometry = validate_route_geometry(
                way_ids, stop_ids, ways, nodes, driving_side=driving_side
            )
        except ValueError as exc:
            context = _geojson([], stop_ids, nodes)
            for way_id in dict.fromkeys(way_ids):
                way = ways[way_id]
                if len(way["nodes"]) >= 2:
                    context["features"].append(
                        track_tools._line_feature(
                            [(nodes[n]["lat"], nodes[n]["lon"]) for n in way["nodes"]],
                            {"way_id": way_id, "name": way["tags"].get("name", "")},
                        )
                    )
            return {
                "success": False,
                "data": {
                    "blocking_issues": [str(exc)],
                    "candidate_geojson": context,
                    "relation_tags": tags,
                    "omitted_stops": omitted,
                    "api_target": config.current_api_base_url,
                    "attribution": ATTRIBUTION,
                },
            }

        members = [
            {
                "type": "node",
                "ref": s["id"],
                "role": s["role"],
                "version": nodes[s["id"]]["version"],
            }
            for s in geometry["stops"]
        ]
        members.extend(
            {"type": "way", "ref": i, "role": "", "version": ways[i]["version"]}
            for i in way_ids
        )
        parents = await read_route_parents(client, members)
        via_ways = await restriction_via_ways(client, parents, ways)
    if before is not None:
        preserve_boarding_roles(before["members"], members, boarding_roles)
        for stop, member in zip(geometry["stops"], members):
            stop["role"] = member["role"]
    duplicates = conflicting_bus_routes(parents, tags, members, before)
    issues = turn_issues(parents, geometry["traversals"], via_ways)
    if duplicates:
        issues.append(f"Existing bus route may cover this direction: {duplicates}")
    if source_basis == "unconfirmed":
        issues.append(
            "Confirm the surveyed itinerary or document permission or a compatible license before uploading"
        )
    geojson = _geojson(geometry["node_ids"], stop_ids, nodes)
    summary = {
        "route": f"Bus {tags.get('ref','')}".strip(),
        "from": tags.get("from"),
        "to": tags.get("to"),
        "stop_members": len(stop_ids),
        "way_members": len(way_ids),
        "length_m": geometry["length_m"],
    }
    comment = (
        f"Update bus route relation/{before['id']}"
        if before
        else f"Add bus route {tags['ref']} from {tags['from']} to {tags['to']}"
    )
    payload = {
        "action": "bus_route_update" if before else "bus_route_create",
        "relation_tags": tags,
        "members": members,
        "geometry_node_versions": {
            str(n): nodes[n]["version"] for w in ways.values() for n in w["nodes"]
        },
        "restriction_versions": restriction_snapshot(parents),
        "restriction_via_versions": {str(k): v["version"] for k, v in via_ways.items()},
        "blocking_issues": issues,
        "source_basis": source_basis,
        "omitted_stops": omitted,
        "driving_side": driving_side,
        "changeset_comment": _text(comment[:255]),
        "changeset_source": source,
        "summary": summary,
        "_review": {"proposed_geojson": geojson},
    }
    data = {
        "summary": summary,
        "relation_tags": tags,
        "members": members,
        "stops": [
            {
                **s,
                "name": nodes[s["id"]]["tags"].get("name"),
                "osm_url": f"{config.current_web_base_url}/node/{s['id']}",
            }
            for s in geometry["stops"]
        ],
        "traversals": geometry["traversals"],
        "omitted_stops": omitted,
        "source": source,
        "source_basis": source_basis,
        "duplicate_relation_ids": duplicates,
        "blocking_issues": issues,
        "proposed_geojson": geojson,
        "api_target": config.current_api_base_url,
        "attribution": ATTRIBUTION,
    }
    if before is not None:
        changes = route_changes(before, tags, members)
        if not changes["tags"] and not changes["members"]:
            issues.append("The proposed route is identical to its current OSM version")
        summary.update(relation_id=before["id"], original_version=before["version"])
        payload["relation_before"] = before
        data.update(relation_before=before, changes=changes)
    if prepare_upload and not issues:
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
        proposal = track_tools._store_proposal(payload, int(identity["user_id"]))
        data.update(
            proposal_id=proposal.proposal_id,
            proposal_digest=proposal.digest,
            preview_uri=f"ui://osm-edit/proposal/{proposal.proposal_id}",
            expires_at_unix=proposal.expires_at,
        )
    return {"success": not issues, "data": data}


def route_review_html(proposal: track_tools.Proposal) -> str:
    payload = proposal.payload
    reviewed = {
        k: payload[k]
        for k in ("relation_tags", "members", "omitted_stops", "changeset_source")
    }
    if "relation_before" in payload:
        reviewed["relation_before"] = payload["relation_before"]
        reviewed["changes"] = route_changes(
            payload["relation_before"], payload["relation_tags"], payload["members"]
        )
    reviewed["stops_in_travel_order"] = [
        feature["properties"]
        for feature in payload["_review"]["proposed_geojson"]["features"]
        if "stop_sequence" in feature["properties"]
    ]
    details = html.escape(json.dumps(reviewed, ensure_ascii=False, indent=2))
    tags = payload["relation_tags"]
    title = (
        f"Update bus route relation/{payload['relation_before']['id']}"
        if "relation_before" in payload
        else f"Bus {tags['ref']} · {tags['from']} → {tags['to']}"
    )
    return track_tools._map_preview_html(
        title,
        {"proposed": payload["_review"]["proposed_geojson"]},
        "<section><p>Review the stops in travel order, the roads and the stated survey source.</p>"
        f"<p>SHA-256 {html.escape(proposal.digest)}</p><pre>{details}</pre></section>",
    )
