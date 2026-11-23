"""Inspect the original relation and review exact ordered changes to a bus direction."""

from collections import Counter, defaultdict, deque
from difflib import SequenceMatcher
from typing import Any, Literal, get_args

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config
from .transit_data import element_tags

BoardingRole = Literal[
    "stop",
    "platform",
    "stop_entry_only",
    "stop_exit_only",
    "platform_entry_only",
    "platform_exit_only",
]
STOP_ROLES = frozenset(get_args(BoardingRole))


async def read_bus_direction(client: Any, relation_id: int) -> dict[str, Any]:
    response = await client.get(f"{config.current_api_base_url}/relation/{relation_id}")
    response.raise_for_status()
    root = parse_xml(response.content)
    if root.tag != "osm" or len(root) != 1 or root[0].tag != "relation":
        raise ValueError(f"Expected one live OSM relation/{relation_id}")
    element = root[0]
    tags = element_tags(element)
    version = int(element.attrib["version"])
    if (
        int(element.attrib["id"]) != relation_id
        or version < 1
        or element.get("visible") == "false"
        or len(element.findall("tag")) != len(tags)
        or (tags.get("type"), tags.get("route"), tags.get("public_transport:version"))
        != ("route", "bus", "2")
    ):
        raise ValueError("Select a visible PTv2 bus direction relation")
    members: list[dict[str, Any]] = []
    roads_started = False
    for member in element.findall("member"):
        kind, role, ref = (
            member.attrib["type"],
            member.attrib["role"],
            int(member.attrib["ref"]),
        )
        if kind == "way" and role == "":
            roads_started = True
        elif kind != "node" or role not in STOP_ROLES or roads_started:
            raise ValueError(
                "This route contains unsupported members, roles or member order. "
                "Updates support node stops/platforms followed by roads with empty roles."
            )
        if ref <= 0 or len(members) >= 850:
            raise ValueError(
                "Existing route exceeds the supported member limits or contains an invalid reference"
            )
        members.append({"type": kind, "ref": ref, "role": role})
    return {"id": relation_id, "version": version, "tags": tags, "members": members}


def preserve_boarding_roles(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    boarding_roles: list[BoardingRole | None] | None = None,
) -> None:
    """Keep restrictions by visit, requiring a decision when a restricted stop moves."""
    original: dict[int, deque[str]] = defaultdict(deque)
    for member in before:
        if member["type"] == "node":
            original[member["ref"]].append(member["role"])
    stops = [member for member in after if member["type"] == "node"]
    if boarding_roles is not None and len(boarding_roles) != len(stops):
        raise ValueError(
            "Provide one boarding_roles entry for each selected stop visit"
        )
    counts = Counter(stop["ref"] for stop in stops)
    changed = {
        ref
        for ref, roles in original.items()
        if len(roles) != counts[ref] and any("_" in role for role in roles)
    }
    restricted_removed = any(len(original[ref]) > counts[ref] for ref in changed)
    for index, stop in enumerate(stops):
        ref = stop["ref"]
        original_role = original[ref].popleft() if original[ref] else None
        explicit = boarding_roles[index] if boarding_roles is not None else None
        if explicit is None and (
            ref in changed or (restricted_removed and original_role is None)
        ):
            raise ValueError(
                f"Changed visit count or replacement of a restricted stop: supply the observed boarding_roles entry for visit {index} (node/{ref})"
            )
        role = explicit or original_role or stop["role"]
        if role not in STOP_ROLES or role.split("_", 1)[0] != stop["role"]:
            raise ValueError(
                f"Role {role} for node/{ref} conflicts with its current OSM stop type"
            )
        stop["role"] = role


def route_changes(
    before: dict[str, Any], tags: dict[str, str], members: list[dict[str, Any]]
) -> dict[str, Any]:
    def member_rows(items: list[dict[str, Any]]) -> list[tuple[str, int, str]]:
        return [(m["type"], m["ref"], m["role"]) for m in items]

    old = before["members"]
    new = [{k: m[k] for k in ("type", "ref", "role")} for m in members]
    matcher = SequenceMatcher(None, member_rows(old), member_rows(new), autojunk=False)
    return {
        "tags": {
            k: {"before": before["tags"].get(k), "after": tags.get(k)}
            for k in sorted(before["tags"].keys() | tags.keys())
            if before["tags"].get(k) != tags.get(k)
        },
        "members": [
            {
                "operation": op,
                "before_range": [a, b],
                "after_range": [c, d],
                "before": old[a:b],
                "after": new[c:d],
            }
            for op, a, b, c, d in matcher.get_opcodes()
            if op != "equal"
        ],
    }
