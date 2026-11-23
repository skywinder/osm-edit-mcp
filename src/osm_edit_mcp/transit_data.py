"""Read current OSM route members and check turn restrictions for a bus journey."""

from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring as parse_xml

from .config import config


def element_tags(element: Element) -> dict[str, str]:
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


async def _bulk_read(
    client: Any, kind: str, ids: set[int]
) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    ordered = sorted(ids)
    for offset in range(0, len(ordered), 150):
        batch = ordered[offset : offset + 150]
        plural = kind + "s"
        response = await client.get(
            f"{config.current_api_base_url}/{plural}",
            params={plural: ",".join(map(str, batch))},
        )
        response.raise_for_status()
        root = parse_xml(response.text)
        if root.tag != "osm":
            raise ValueError(f"Invalid OSM {plural} response")
        found = set()
        for element in root.findall(kind):
            identifier = int(element.attrib["id"])
            version = int(element.attrib["version"])
            if element.get("visible") == "false" or version < 1 or identifier in found:
                raise ValueError(f"Invalid or deleted {kind} {identifier}")
            found.add(identifier)
            record: dict[str, Any] = {
                "id": identifier,
                "version": version,
                "tags": element_tags(element),
            }
            if kind == "way":
                record["nodes"] = [
                    int(nd.attrib["ref"]) for nd in element.findall("nd")
                ]
            else:
                record.update(
                    lat=float(element.attrib["lat"]), lon=float(element.attrib["lon"])
                )
            records[identifier] = record
        if found != set(batch):
            raise ValueError(f"Incomplete live OSM {plural} response")
    return records


async def fetch_route_objects(
    client: Any, way_ids: list[int], stop_ids: list[int]
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    ways = await _bulk_read(client, "way", set(way_ids))
    node_ids = {n for w in ways.values() for n in w["nodes"]}.union(stop_ids)
    if len(node_ids) > 12000:
        raise ValueError("Route exceeds the 12000-node geometry review limit")
    return ways, await _bulk_read(client, "node", node_ids)


_BUS_MODES = ("bus", "psv", "motor_vehicle", "vehicle")


def _bus_restrictions(relation: Element) -> list[str]:
    tags = element_tags(relation)
    kind = tags.get("type", "")
    if kind not in {"restriction", *("restriction:" + mode for mode in _BUS_MODES)}:
        return []
    if set(_BUS_MODES).intersection(
        item.strip() for item in tags.get("except", "").split(";")
    ):
        return []
    for key in ["restriction:" + mode for mode in _BUS_MODES] + ["restriction"]:
        unconditional = tags.get(key, "")
        conditional = tags.get(key + ":conditional", "")
        if unconditional or conditional:
            return [
                value
                for value in [
                    unconditional,
                    *[part.split("@")[0].strip() for part in conditional.split(";")],
                ]
                if value
            ]
    return []


def restriction_snapshot(parents: dict[int, Element]) -> dict[str, int]:
    return {
        str(identifier): int(rel.attrib["version"])
        for identifier, rel in parents.items()
        if _bus_restrictions(rel)
    }


async def restriction_via_ways(
    client: Any, parents: dict[int, Element], ways: dict[int, dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    """Read off-route via ways so an only-turn on the *other* end of a road is harmless."""
    required = {
        int(m.attrib["ref"])
        for rel in parents.values()
        if any(rule.startswith("only_") for rule in _bus_restrictions(rel))
        for m in rel.findall("member")
        if m.get("role") == "via" and m.get("type") == "way"
    }
    extra = await _bulk_read(client, "way", required - ways.keys())
    return {i: (extra[i] if i in extra else ways[i]) for i in required}


def turn_issues(
    parents: dict[int, Element],
    traversals: list[dict[str, Any]],
    via_geometry: dict[int, dict[str, Any]] | None = None,
) -> list[str]:
    """Evaluate node and via-way restrictions against the directed itinerary."""
    way_ids = [t["way_id"] for t in traversals]
    issues = []
    for identifier, relation in parents.items():
        rules = _bus_restrictions(relation)
        if not rules:
            continue
        members = relation.findall("member")

        def refs(role: str, kind: str) -> list[int]:
            return [
                int(m.attrib["ref"])
                for m in members
                if m.get("role") == role and m.get("type") == kind
            ]

        starts, ends = refs("from", "way"), refs("to", "way")
        via_ways, via_nodes = refs("via", "way"), refs("via", "node")
        for i, start in enumerate(way_ids[:-1]):
            if start not in starts:
                continue
            if via_nodes and traversals[i]["to_node"] not in via_nodes:
                continue
            if not ends or (not via_nodes and not via_ways) or (via_nodes and via_ways):
                issues.append(
                    f"Review malformed turn restriction relation/{identifier}"
                )
                break
            if via_ways:
                approach = (via_geometry or {}).get(via_ways[0])
                if (
                    approach is not None
                    and traversals[i]["to_node"] not in approach["nodes"]
                ):
                    continue
                following_ways = way_ids[i + 1 : i + 1 + len(via_ways)]
                if following_ways != via_ways[: len(following_ways)]:
                    if any(rule.startswith("only_") for rule in rules):
                        issues.append(
                            f"Review departure from only-turn restriction relation/{identifier}"
                        )
                    continue
            following = i + 1 + len(via_ways)
            if following >= len(way_ids):
                continue
            uses_to = way_ids[following] in ends
            if any(
                (rule.startswith("no_") and uses_to)
                or (rule.startswith("only_") and not uses_to)
                or not rule.startswith(("no_", "only_"))
                for rule in rules
            ):
                issues.append(
                    f"Bus movement on way/{start} conflicts with turn restriction relation/{identifier}"
                )
                break
    return sorted(set(issues))
