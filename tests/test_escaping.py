"""Tests for XML and query escaping of user-supplied values.

Tag values reach the server from natural-language input and routinely contain
quotes and ampersands. Before these fixes they were interpolated raw into OSM
XML and into Overpass QL.
"""
import xml.etree.ElementTree as ET

import pytest

from src.osm_edit_mcp.server import build_tags_xml, overpass_literal


def test_tags_with_quotes_produce_well_formed_xml():
    """A name containing double quotes must not break out of the attribute."""
    tags = {"name": 'Bob\'s "Best" Fish & Chips', "amenity": "restaurant"}

    xml = f"<osm><node>{build_tags_xml(tags)}</node></osm>"
    parsed = ET.fromstring(xml)  # raises if malformed

    recovered = {t.get("k"): t.get("v") for t in parsed.findall(".//tag")}
    assert recovered == tags


def test_tag_value_cannot_inject_extra_elements():
    """A crafted value must stay a value, not become new XML elements."""
    tags = {"name": '"/><tag k="highway" v="motorway"/><x y="'}

    xml = f"<osm><node>{build_tags_xml(tags)}</node></osm>"
    parsed = ET.fromstring(xml)

    tag_elements = parsed.findall(".//tag")
    assert len(tag_elements) == 1
    assert tag_elements[0].get("k") == "name"
    assert "highway" not in {t.get("k") for t in tag_elements}


def test_tag_key_is_escaped_too():
    tags = {'weird"key': "value"}

    parsed = ET.fromstring(f"<osm><node>{build_tags_xml(tags)}</node></osm>")

    assert parsed.find(".//tag").get("k") == 'weird"key'


def test_angle_brackets_and_ampersands_round_trip():
    tags = {"description": "A & B <not a tag> 'quoted'"}

    parsed = ET.fromstring(f"<osm><node>{build_tags_xml(tags)}</node></osm>")

    assert parsed.find(".//tag").get("v") == "A & B <not a tag> 'quoted'"


def test_empty_tags_produce_empty_string():
    assert build_tags_xml({}) == ""


def test_non_string_values_are_coerced():
    parsed = ET.fromstring(f"<osm><node>{build_tags_xml({'level': 2})}</node></osm>")

    assert parsed.find(".//tag").get("v") == "2"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('say "hi"', 'say \\"hi\\"'),
        ("back\\slash", "back\\\\slash"),
        ("plain", "plain"),
    ],
)
def test_overpass_literal_escapes_quotes_and_backslashes(raw, expected):
    """An unescaped quote would terminate the Overpass string early."""
    assert overpass_literal(raw) == expected


def test_overpass_literal_neutralises_query_break_out():
    escaped = overpass_literal('cafe"](around:1,0,0);out count;//')

    # The embedded quote is escaped, so it cannot close the QL string literal.
    assert '"]' not in escaped.replace('\\"', "")
