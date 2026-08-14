"""OSM XML serialization and parsing helpers."""

import xml.etree.ElementTree as ET
from typing import Any, Dict

from defusedxml.ElementTree import fromstring as parse_xml
from xml.sax.saxutils import quoteattr

def build_tags_xml(tags: Dict[str, str]) -> str:
    """Serialise a tag dict into OSM <tag> elements with proper XML escaping.

    Tag keys and values come from user or model input and routinely contain
    characters that are special in XML - a name like `Bob's "Best" Fish & Chips`
    would otherwise produce malformed XML or inject extra elements into the
    changeset.
    """
    return "".join(
        f'<tag k={quoteattr(str(key))} v={quoteattr(str(value))}/>'
        for key, value in tags.items()
    )


def parse_osm_xml(xml_content: str) -> Dict[str, Any]:
    """Parse OSM XML response into JSON format."""
    try:
        root = parse_xml(xml_content)
        result: Dict[str, Any] = {"elements": []}

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
                }  # type: Dict[str, Any]

                if element.tag == "node":
                    elem_data["lat"] = float(element.get("lat", 0))
                    elem_data["lon"] = float(element.get("lon", 0))
                elif element.tag == "way":
                    # A malformed <nd> without a ref would otherwise raise
                    # TypeError from int(None) and fail the whole parse.
                    elem_data["nodes"] = [
                        int(ref) for ref in (nd.get("ref") for nd in element.findall("nd"))
                        if ref is not None
                    ]
                elif element.tag == "relation":
                    elem_data["members"] = []
                    for member in element.findall("member"):
                        ref = member.get("ref")
                        if ref is None:
                            continue
                        elem_data["members"].append({
                            "type": member.get("type"),
                            "ref": int(ref),
                            "role": member.get("role", "")
                        })

                # Parse tags
                for tag in element.findall("tag"):
                    elem_data["tags"][tag.get("k")] = tag.get("v")

                result["elements"].append(elem_data)

        return result
    except ET.ParseError as e:
        return {"error": f"Failed to parse XML: {str(e)}"}
