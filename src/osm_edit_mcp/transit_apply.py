"""Publish and verify a reviewed bus relation or a supporting road split."""

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Any

from defusedxml.ElementTree import fromstring as parse_xml
from mcp.server.fastmcp import Context

from . import track_tools
from .auth import verify_write_identity
from .config import config
from .http_client import describe_exception, get_authenticated_client, get_public_client
from .proposal_store import StoredProposal, canonical_digest
from .transit_data import (
    element_tags,
    fetch_route_objects,
    restriction_snapshot,
    restriction_via_ways,
)


def _members(element: ET.Element) -> list[tuple[str, int, str]]:
    return [
        (member.attrib["type"], int(member.attrib["ref"]), member.attrib["role"])
        for member in element.findall("member")
    ]


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


async def read_route_parents(
    client: Any, members: list[dict[str, Any]]
) -> dict[int, ET.Element]:
    """Read current parent relations for every way and both terminal stops."""
    ways = [("way", m["ref"]) for m in members if m["type"] == "way"]
    stops = [("node", m["ref"]) for m in members if m["type"] == "node"]
    anchors = list(dict.fromkeys(ways + stops[:1] + stops[-1:]))
    parents: dict[int, ET.Element] = {}

    async def fetch(kind: str, ref: int) -> list[ET.Element]:
        response = await client.get(
            f"{config.current_api_base_url}/{kind}/{ref}/relations"
        )
        response.raise_for_status()
        root = parse_xml(response.content)
        if root.tag != "osm" or any(child.tag != "relation" for child in root):
            raise ValueError("Invalid OSM parent relation response")
        return list(root)

    # The OSM API permits two download slots. Do not queue a task per way.
    for start in range(0, len(anchors), 2):
        groups = await asyncio.gather(*(fetch(*a) for a in anchors[start : start + 2]))
        for group in groups:
            for relation in group:
                ref = int(relation.attrib["id"])
                if ref in parents and parents[ref].get("version") != relation.get(
                    "version"
                ):
                    raise ValueError("An OSM parent relation changed during inspection")
                parents[ref] = relation
    return parents


def duplicate_route_ids(
    parents: dict[int, ET.Element], tags: dict[str, str], members: list[dict[str, Any]]
) -> list[int]:
    """Find potential same-direction relations, including legacy or incomplete ones."""
    origin = _normalized_text(tags["from"])
    destination = _normalized_text(tags["to"])
    ref = _normalized_text(tags["ref"])
    stops = [m["ref"] for m in members if m["type"] == "node"]
    ways = [m["ref"] for m in members if m["type"] == "way"]
    duplicates = []
    for relation_id, relation in parents.items():
        other = element_tags(relation)
        if other.get("type") != "route" or other.get("route") != "bus":
            continue
        refs = _members(relation)
        other_ways = [
            v for k, v, role in refs if k == "way" and not role.startswith("platform")
        ]
        other_stops = [v for k, v, _ in refs if k == "node"]
        endpoints = tuple(_normalized_text(other.get(k, "")) for k in ("from", "to"))
        existing_ref = _normalized_text(other.get("ref", ""))
        if existing_ref and existing_ref != ref:
            continue
        same_terminals = (
            stops
            and other_stops
            and (other_stops[0], other_stops[-1]) == (stops[0], stops[-1])
        )
        reverse_terminals = (
            len(other_stops) > 1
            and stops
            and stops[0] != stops[-1]
            and (other_stops[0], other_stops[-1]) == (stops[-1], stops[0])
        )
        if (
            origin != destination
            and endpoints == (destination, origin)
            and not same_terminals
        ):
            continue
        if reverse_terminals and endpoints != (origin, destination):
            continue
        # Some legacy relations put the route number only in the name.
        legacy_bus_name = not existing_ref and re.search(
            r"(?:\b(?:bus|автобус(?:и)?)\s*№?\s*|^\s*№?\s*)"
            + re.escape(ref)
            + r"(?!\w)",
            _normalized_text(other.get("name", "")),
        )
        if (
            existing_ref == ref
            or legacy_bus_name
            or endpoints == (origin, destination)
            or (stops and other_stops == stops)
            or (ways and other_ways == ways)
        ):
            duplicates.append(relation_id)
    return sorted(duplicates)


def _transit_proposal(proposal_id: str) -> StoredProposal:
    p = track_tools._PROPOSAL_STORE.get(proposal_id, include_expired=True)
    if p is None or p.payload.get("action") not in {
        "bus_route_create",
        "bus_way_split",
    }:
        raise ValueError("Unknown transit proposal")
    if p.api_target != config.current_api_base_url or p.osm_uid is None:
        raise ValueError("Proposal is unbound or belongs to another OSM API")
    if p.digest != canonical_digest(p.payload, p.api_target, p.osm_uid):
        raise ValueError("Stored route proposal digest mismatch")
    if (
        p.payload["action"] == "bus_way_split"
        and p.payload.get("split_osm_uid") != p.osm_uid
    ):
        raise ValueError("Split snapshot belongs to another OSM account")
    return p


async def _check_live_route(client: Any, payload: dict[str, Any]) -> None:
    members, tags = payload["members"], payload["relation_tags"]
    way_ids = [m["ref"] for m in members if m["type"] == "way"]
    stop_ids = [m["ref"] for m in members if m["type"] == "node"]
    ways, nodes = await fetch_route_objects(client, way_ids, stop_ids)
    for m in members:
        actual = (ways if m["type"] == "way" else nodes)[m["ref"]]
        if actual["version"] != m["version"]:
            raise ValueError(f"Version changed for {m['type']} {m['ref']}")
    shape_versions = {
        str(n): nodes[n]["version"] for way in ways.values() for n in way["nodes"]
    }
    if shape_versions != payload["geometry_node_versions"]:
        raise ValueError("Route geometry nodes changed since preview")
    parents = await read_route_parents(client, members)
    if restriction_snapshot(parents) != payload["restriction_versions"]:
        raise ValueError("Turn restrictions changed since preview")
    via_ways = await restriction_via_ways(client, parents, ways)
    if {str(k): v["version"] for k, v in via_ways.items()} != payload.get(
        "restriction_via_versions", {}
    ):
        raise ValueError("Turn restriction via ways changed since preview")
    duplicates = duplicate_route_ids(parents, tags, members)
    if duplicates:
        raise ValueError(f"Possible existing bus route relations: {duplicates}")


def _route_xml(payload: dict[str, Any], changeset_id: int) -> str:
    root = ET.Element(
        "osmChange", version="0.6", generator=config.default_changeset_created_by
    )
    relation = ET.SubElement(
        ET.SubElement(root, "create"), "relation", id="-1", changeset=str(changeset_id)
    )
    for m in payload["members"]:
        ET.SubElement(
            relation, "member", type=m["type"], ref=str(m["ref"]), role=m["role"]
        )
    track_tools._append_tags(relation, payload["relation_tags"])
    return ET.tostring(root, encoding="unicode")


def _validate_created(
    element: ET.Element,
    p: StoredProposal,
    changeset: int,
    relation_id: int,
) -> None:
    expected = [(m["type"], m["ref"], m["role"]) for m in p.payload["members"]]
    if (
        element.tag != "relation"
        or int(element.get("id", "0")) != relation_id
        or int(element.get("version", "0")) != 1
        or int(element.get("changeset", "0")) != changeset
        or int(element.get("uid", "0")) != p.osm_uid
        or element.get("visible") == "false"
        or _members(element) != expected
        or element_tags(element) != p.payload["relation_tags"]
        or len(element.findall("tag")) != len(p.payload["relation_tags"])
    ):
        raise ValueError("OSM relation differs from the approved creation")


async def _readback(
    client: Any, p: StoredProposal, changeset: int, relation_id: int
) -> None:
    response = await client.get(f"{p.api_target}/relation/{relation_id}")
    response.raise_for_status()
    root = parse_xml(response.content)
    if root.tag != "osm" or len(root) != 1:
        raise ValueError("Expected one OSM relation in readback")
    _validate_created(root[0], p, changeset, relation_id)


async def _verified_objects(
    client: Any, p: StoredProposal, changeset: int, diff: list[dict[str, Any]]
) -> dict[str, Any]:
    if p.payload["action"] == "bus_way_split":
        from .transit_split import verify_split_diff

        check = await verify_split_diff(client, p.payload, diff, changeset)
        if check["status"] != "verified":
            raise ValueError(f"Road split verification incomplete: {check['failures']}")
        return {
            "verification": check,
            "way_ids": [row["new_id"] for row in check["verified"]],
        }
    if (
        len(diff) != 1
        or diff[0]["type"] != "relation"
        or diff[0]["old_id"] != -1
        or diff[0]["new_version"] != 1
        or diff[0]["new_id"] <= 0
    ):
        raise ValueError("Upload did not return the expected relation mapping")
    relation_id = diff[0]["new_id"]
    await _readback(client, p, changeset, relation_id)
    return {
        "verification": {"status": "verified", "version": 1},
        "relation_id": relation_id,
        "relation_url": f"{config.current_web_base_url}/relation/{relation_id}",
    }


def _receipt(
    p: StoredProposal,
    changeset: int,
    diff: list[dict[str, Any]],
    verified: dict[str, Any],
    closed: bool,
) -> dict[str, Any]:
    return {
        "proposal_id": p.proposal_id,
        "proposal_digest": p.digest,
        "api_target": p.api_target,
        "osm_uid": p.osm_uid,
        "changeset_id": changeset,
        "changeset_url": f"{config.current_web_base_url}/changeset/{changeset}",
        "changeset_closed": closed,
        "diff_results": diff,
        **verified,
        "summary": p.payload["summary"],
    }


async def apply_transit_edit(
    proposal_id: str,
    proposal_digest: str,
    context: Context,
    changeset_id: int | None = None,
) -> dict[str, Any]:
    """Internal dispatch from apply_osm_edit; the same host confirms this exact digest."""
    store = track_tools._PROPOSAL_STORE
    claimed = False
    upload_started = False
    changeset = None
    closed = False
    try:
        p = _transit_proposal(proposal_id)
        if proposal_digest != p.digest or changeset_id is not None:
            raise ValueError(
                "Exact reviewed digest and a dedicated changeset are required"
            )
        if p.status == "APPLIED" and p.receipt:
            return {
                "success": True,
                "data": p.receipt,
                "message": "Transit proposal already applied",
            }
        if p.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
            return {
                "success": False,
                "error": "Proposal unavailable",
                "status": p.status,
            }
        if p.payload["blocking_issues"] != []:
            return {
                "success": False,
                "error": "Transit preview is blocked",
                "blocking_issues": p.payload["blocking_issues"],
            }
        rejection = await track_tools._request_host_confirmation(p, context)
        if rejection is not None:
            return rejection
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
            p = store.claim(
                p.proposal_id,
                p.digest,
                config.current_api_base_url,
                int(identity["user_id"]),
            )
            if p.status == "APPLIED" and p.receipt:
                return {
                    "success": True,
                    "data": p.receipt,
                    "message": "Transit proposal already applied",
                }
            claimed = True
            if p.payload["action"] == "bus_way_split":
                from .transit_split import validate_split_context

                await validate_split_context(client, p.payload)
                build_xml = track_tools._build_osm_change
            else:
                await _check_live_route(client, p.payload)
                build_xml = _route_xml
            changeset = await track_tools._create_owned_changeset(client, p.payload)
            if changeset <= 0:
                raise ValueError("OSM did not return a positive changeset ID")
            try:
                store.bind_transit_changeset(proposal_id, changeset)
                xml = build_xml(p.payload, changeset)
                upload_started = True
                response = await client.post(
                    f"{p.api_target}/changeset/{changeset}/upload",
                    content=xml,
                    headers={"Content-Type": "text/xml"},
                )
                if response.status_code in {
                    400,
                    401,
                    403,
                    404,
                    405,
                    409,
                    410,
                    412,
                    413,
                    415,
                    422,
                    429,
                }:
                    # The editing API rejected this atomic upload before committing.
                    upload_started = False
                response.raise_for_status()
                diff = track_tools._parse_diff_result(response.text)
                verified = await _verified_objects(client, p, changeset, diff)
            finally:
                try:
                    closed = await track_tools._close_owned_changeset(client, changeset)
                except Exception:
                    closed = False
        receipt = _receipt(p, changeset, diff, verified, closed)
        store.finish(proposal_id, "APPLIED", receipt=receipt)
        return {
            "success": True,
            "data": receipt,
            "message": "Transit edit uploaded and verified",
        }
    except asyncio.CancelledError:
        if claimed:
            store.finish(
                proposal_id,
                "RECONCILE_REQUIRED" if upload_started else "FAILED",
                receipt={"changeset_id": changeset, "changeset_closed": closed},
                error="Request cancelled",
            )
        raise
    except Exception as exc:
        error = describe_exception(exc)
        partial = {"changeset_id": changeset, "changeset_closed": closed}
        if claimed:
            status = "RECONCILE_REQUIRED" if upload_started else "FAILED"
            store.finish(proposal_id, status, receipt=partial, error=error)
            return {"success": False, "error": error, "status": status, "data": partial}
        return {"success": False, "error": error}


async def verify_transit_edit(proposal_id: str) -> dict[str, Any]:
    """Verify the approved objects or recover their mappings from the dedicated changeset."""
    try:
        p = _transit_proposal(proposal_id)
        changeset = p.changeset_id
        if not changeset or p.status not in {
            "APPLIED",
            "APPLYING",
            "RECONCILE_REQUIRED",
        }:
            return {
                "success": False,
                "error": "No transit upload to verify",
                "status": p.status,
            }
        if p.status == "APPLIED" and p.receipt:
            async with get_public_client() as client:
                await _verified_objects(client, p, changeset, p.receipt["diff_results"])
            return {"success": True, "data": p.receipt}
        async with get_authenticated_client() as client:
            identity = await verify_write_identity(client)
            if int(identity["user_id"]) != p.osm_uid:
                raise ValueError(
                    "Bus route proposal belongs to a different OSM account"
                )
            response = await client.get(
                f"{p.api_target}/changeset/{changeset}/download"
            )
            response.raise_for_status()
            change = parse_xml(response.content)
            objects = [(op.tag, obj) for op in change for obj in op]
            if change.tag != "osmChange":
                raise ValueError("Invalid changeset download response")
            if not objects:
                # A lost response can correspond to a commit still in progress. Only
                # an explicitly closed, empty changeset proves no upload took effect.
                info = await client.get(f"{p.api_target}/changeset/{changeset}")
                info.raise_for_status()
                meta = parse_xml(info.content).find("changeset")
                if (
                    meta is not None
                    and meta.get("id") == str(changeset)
                    and meta.get("uid") == str(p.osm_uid)
                    and meta.get("open") == "false"
                    and meta.get("changes_count") == "0"
                ):
                    track_tools._PROPOSAL_STORE.release_empty_transit_changeset(p)
                    return {
                        "success": False,
                        "status": "FAILED",
                        "error": "The dedicated changeset closed without an edit",
                        "changeset_id": changeset,
                    }
                raise ValueError(
                    "Changeset has no confirmed edit and its outcome is unresolved"
                )
            if p.payload["action"] == "bus_way_split":
                from .transit_split import split_diff_from_download

                diff = split_diff_from_download(response.content, p.payload, changeset)
            else:
                if len(objects) != 1 or objects[0][0] != "create":
                    raise ValueError(
                        "Dedicated changeset does not show exactly one creation"
                    )
                relation = objects[0][1]
                relation_id = int(relation.attrib["id"])
                _validate_created(relation, p, changeset, relation_id)
                diff = [
                    {
                        "type": "relation",
                        "old_id": -1,
                        "new_id": relation_id,
                        "new_version": 1,
                    }
                ]
            verified = await _verified_objects(client, p, changeset, diff)
        receipt = _receipt(
            p,
            changeset,
            diff,
            verified,
            (p.receipt or {}).get("changeset_closed", False),
        )
        reconciled = track_tools._PROPOSAL_STORE.record_reconciliation(
            proposal_id,
            p.digest,
            p.api_target,
            int(identity["user_id"]),
            receipt,
            allow_applying=True,
        )
        return {
            "success": True,
            "data": reconciled.receipt,
            "message": "Transit edit verified from its changeset",
        }
    except Exception as exc:
        return {"success": False, "error": describe_exception(exc)}
