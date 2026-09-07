"""Offline regression coverage for bounded multilingual name searches."""

import json
import re

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tag,term",
    [
        ("name:en", "Matenadaran"),
        ("name:ru", "Матенадаран"),
        ("name", "Matenadaran"),
        ("alt_name", "Matenadaran"),
        ("alt_name:en", "Matenadaran"),
        ("official_name", "Матенадаран"),
        ("official_name:ru", "Матенадаран"),
        ("name:en", 'Matenadaran.*[x]"\\'),
    ],
)
@pytest.mark.parametrize(
    "scope,bound",
    [
        ({"bbox": "44.50,40.19,44.52,40.21"}, "(40.19,44.5,40.21,44.52)"),
        (
            {"lat": 40.2, "lon": 44.51, "radius_meters": 1200},
            "(around:1200,40.2,44.51)",
        ),
    ],
)
async def test_bounded_search_matches_multilingual_name_tags(
    monkeypatch, tag, term, scope, bound
):
    from src.osm_edit_mcp import read_tools

    fixture = {
        "type": "node",
        "id": 123,
        "lat": 40.2,
        "lon": 44.51,
        "tags": {"name": "Մատենադարան", tag: term},
    }
    queries = []

    async def offline_overpass(query):
        queries.append(query)
        # Interpret only the emitted name key/value regex, never contact Overpass.
        quoted = r'"(?:[^"\\]|\\.)*"'
        match = re.search(r'\[~(' + quoted + r')~(' + quoted + r'),i\]', query)
        if match is None:
            return {"elements": []}
        key_pattern, value_pattern = map(json.loads, match.groups())
        assert key_pattern == "^(name|alt_name|official_name)(:.*)?$"
        assert value_pattern == re.escape(term)
        assert not any(
            re.search(key_pattern, key)
            for key in ("description", "operator:name", "nameplate", "old_name")
        )
        matched = any(
            re.search(key_pattern, key) and re.search(value_pattern, value, re.I)
            for key, value in fixture["tags"].items()
        )
        return {"elements": [fixture] if matched else []}

    monkeypatch.setattr(read_tools, "execute_overpass", offline_overpass)
    result = await read_tools.search_osm_elements(term, element_type="node", **scope)
    assert result["success"], result
    assert [element["id"] for element in result["data"]["elements"]] == [123]
    assert result["data"]["elements"][0]["tags"][tag] == term
    query = queries[0]
    assert "nwr" not in query
    assert query.count(bound) == 6
    literal = json.dumps(re.escape(term), ensure_ascii=False)
    for key in ("amenity", "tourism", "leisure", "historic", "shop"):
        assert f'node["{key}"~{literal},i]{bound};' in query
