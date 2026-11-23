"""Group existing, separately reviewed bus directions in a new route master."""

import html
import json
from typing import Annotated, Any, Literal

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.types import ToolAnnotations
from pydantic import Field

from . import track_tools
from .app import profile_tool
from .auth import verify_write_identity
from .config import config
from .http_client import describe_exception, get_authenticated_client, get_public_client
from .node_tools import _text as check_text
from .transit_data import element_tags
from .transit_tools import Label, ObjectId


async def _directions(client: Any, ids: list[int]) -> list[dict[str, Any]]:
    response = await client.get(
        f"{config.current_api_base_url}/relations",
        params={"relations": ",".join(map(str, ids))},
    )
    response.raise_for_status()
    root = parse_xml(response.content)
    by_id = {int(child.attrib["id"]): child for child in root}
    if root.tag != "osm" or set(by_id) != set(ids) or len(root) != len(ids):
        raise ValueError("Expected every selected direction exactly once from OSM")
    rows = []
    for ref in ids:
        rel = by_id[ref]
        tags = element_tags(rel)
        version = int(rel.attrib["version"])
        if (
            rel.tag != "relation"
            or rel.get("visible") == "false"
            or version < 1
            or tags.get("type") != "route"
            or tags.get("route") != "bus"
            or tags.get("public_transport:version") != "2"
            or not tags.get("ref", "").strip()
            or not any(
                m.get("type") == "way" and m.get("role") == ""
                for m in rel.findall("member")
            )
        ):
            raise ValueError(
                f"Relation {ref} must be a visible PTv2 bus route with a ref and road members"
            )
        response = await client.get(
            f"{config.current_api_base_url}/relation/{ref}/relations"
        )
        response.raise_for_status()
        parents = parse_xml(response.content)
        if parents.tag != "osm" or any(p.tag != "relation" for p in parents):
            raise ValueError(f"Invalid parent relation response for {ref}")
        masters = sorted(
            int(p.attrib["id"])
            for p in parents
            if element_tags(p).get("type") == "route_master"
        )
        rows.append(
            {
                "relation_id": ref,
                "version": version,
                "existing_master_ids": masters,
                "tags": {
                    k: tags[k]
                    for k in ("ref", "from", "to", "via", "name", "operator", "network")
                    if k in tags
                },
            }
        )
    return rows


async def validate_master_context(client: Any, payload: dict[str, Any]) -> None:
    rows = await _directions(client, [m["ref"] for m in payload["members"]])
    if rows != payload["directions"] or any(row["existing_master_ids"] for row in rows):
        raise ValueError(
            "A direction or its route master changed. Review a fresh proposal."
        )


@profile_tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=True
    )
)
async def preview_bus_route_master(
    route_relation_ids: Annotated[list[ObjectId], Field(min_length=2, max_length=50)],
    source: Label,
    source_basis: Literal[
        "survey", "local_knowledge", "compatible_license", "permission", "unconfirmed"
    ] = "unconfirmed",
    name: Label | None = None,
    prepare_upload: bool = False,
) -> dict[str, Any]:
    """Review grouping independently checked PTv2 bus directions or variants of one line.
    Supply existing direction relation IDs in the desired member order and the source
    confirming they belong together. Inspect terminals, tags and existing master IDs.
    An eligible preview with prepare_upload=true can be applied using apply_osm_edit.
    """
    try:
        if not 2 <= len(route_relation_ids) <= 50 or len(
            set(route_relation_ids)
        ) != len(route_relation_ids):
            raise ValueError("Select 2–50 distinct direction relations")
        check_text(source)
        async with get_public_client() as client:
            rows = await _directions(client, route_relation_ids)
        ref = rows[0]["tags"]["ref"]
        issues = []
        if any(row["tags"]["ref"] != ref for row in rows):
            issues.append("The route references differ")
        existing = sorted(
            {master_id for row in rows for master_id in row["existing_master_ids"]}
        )
        if existing:
            issues.append(
                f"Review the existing route masters {existing} before grouping directions"
            )
        if source_basis == "unconfirmed":
            issues.append("Confirm that these directions belong to the same line")
        tags = {"type": "route_master", "route_master": "bus", "ref": ref}
        if name is not None:
            check_text(name)
            tags["name"] = name
        for key in ("network", "operator"):
            values = {row["tags"].get(key) for row in rows}
            if len(values) == 1 and None not in values:
                tags[key] = rows[0]["tags"][key]
            if key == "network" and len(values - {None}) > 1:
                issues.append("Selected directions have different mapped networks")
        members = [
            {
                "type": "relation",
                "ref": row["relation_id"],
                "role": "",
                "version": row["version"],
            }
            for row in rows
        ]
        summary = {
            "route_master": "bus",
            "ref": ref,
            "direction_relations": route_relation_ids,
        }
        data: dict[str, Any] = {
            "summary": summary,
            "relation_tags": tags,
            "members": members,
            "directions": rows,
            "existing_master_ids": existing,
            "existing_master_urls": [
                f"{config.current_web_base_url}/relation/{master_id}"
                for master_id in existing
            ],
            "blocking_issues": issues,
            "api_target": config.current_api_base_url,
            "source": source,
            "source_basis": source_basis,
        }
        if prepare_upload and not issues:
            comment = f"Group directions of bus {ref} in a route master"
            check_text(comment)
            payload = {
                "action": "bus_route_master_create",
                "directions": rows,
                "relation_tags": tags,
                "members": members,
                "summary": summary,
                "blocking_issues": issues,
                "changeset_source": source,
                "source_basis": source_basis,
                "changeset_comment": comment,
            }
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
    except Exception as exc:
        return track_tools._failure(
            type(exc).__name__,
            "Could not prepare the bus route master",
            detail=describe_exception(exc),
        )


def master_review_html(proposal: track_tools.Proposal) -> str:
    payload = proposal.payload
    reviewed = {
        key: payload[key]
        for key in ("relation_tags", "members", "directions", "changeset_source")
    }
    links = []
    for row in payload["directions"]:
        ref = row["relation_id"]
        tags = row["tags"]
        label = tags.get("name") or " → ".join(
            tags[key] for key in ("from", "to") if key in tags
        )
        url = html.escape(f"{config.current_web_base_url}/relation/{ref}", quote=True)
        links.append(
            f'<li><a href="{url}">OSM relation {ref}</a> {html.escape(label)}</li>'
        )
    return (
        "<!doctype html><meta charset=utf-8><title>Review bus route master</title>"
        "<h1>Review bus route master</h1><ol>"
        + "".join(links)
        + "</ol><pre>"
        + html.escape(json.dumps(reviewed, indent=2, ensure_ascii=False))
        + "</pre><p>SHA-256 "
        + html.escape(proposal.digest)
        + "</p>"
    )
