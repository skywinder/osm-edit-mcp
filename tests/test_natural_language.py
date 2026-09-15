"""Regression cases from mapper feedback (#11); no network or write calls."""

import pytest

from src.osm_edit_mcp import read_tools
from src.osm_edit_mcp.natural_language import extract_action_from_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text, expected",
    [
        ("a public footpath that follows the old railway line", {}),
        ("a car park for a garden centre", {"amenity": "parking"}),
        ("a pub called The Red Lion", {"amenity": "pub"}),
        ("A CAR   PARK", {"amenity": "parking"}),
        ("a cafe that is inaccessible", {"amenity": "cafe"}),
        (
            "a cafe that is not wheelchair accessible",
            {"amenity": "cafe", "wheelchair": "no"},
        ),
        (
            "a cafe that is wheelchair accessible",
            {"amenity": "cafe", "wheelchair": "yes"},
        ),
        ("a cafe with no wifi", {"amenity": "cafe", "internet_access": "no"}),
        (
            "a cafe with free wifi",
            {"amenity": "cafe", "internet_access": "wlan", "internet_access:fee": "no"},
        ),
        (
            "a cafe with no takeaway and no outdoor seating",
            {"amenity": "cafe", "takeaway": "no", "outdoor_seating": "no"},
        ),
        ("a cafe with delivery", {"amenity": "cafe", "delivery": "yes"}),
        ("a subway station", {"railway": "station", "station": "subway"}),
        ("a pub, near the railway", {"amenity": "pub"}),
        ("a public republic", {}),
    ],
)
async def test_tag_suggestions_respect_words_and_specific_phrases(text, expected):
    result = await read_tools.parse_natural_language_osm_request(text)
    assert result["success"] is True
    assert result["data"]["suggested_tags"] == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a public footpath", "find"),
        ("a cafe with outdoor seating", "find"),
        ("add a cafe", "create"),
        ("remove a cafe", "delete"),
        ("modify a cafe", "update"),
        ("look for a pub", "find"),
    ],
)
def test_actions_are_whole_words(text, expected):
    assert extract_action_from_text(text) == expected
