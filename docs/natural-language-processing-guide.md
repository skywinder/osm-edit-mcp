# Natural-language requests

OSM Edit MCP has one registered natural-language MCP tool:
`parse_natural_language_osm_request`. It is a read-only heuristic parser. It
can identify a likely intent and suggest candidate tags, but it never selects an
OSM object, creates a proposal, or writes to OpenStreetMap.

## Parse an intent

```text
parse_natural_language_osm_request(
  request="Find cafes with outdoor seating near the station"
)
```

A successful response contains:

- `parsed_request`: the parser's interpretation of action, feature type, name,
  location text, and attributes;
- `suggested_tags`: candidate OSM tags inferred from recognized phrases;
- `action_suggestions`: safe next-step guidance.

Treat every field as a suggestion. The parser is rule-based, can miss regional
meaning, and does not prove that a tag is current or appropriate.

## Safe next steps

For discovery, use registered read tools such as:

```text
search_osm_elements(query="cafe", element_type="all")
get_place_info(place_name="Central Station")
```

Inspect exact OSM IDs, versions, tags, and geometry before drawing conclusions.
Natural-language descriptions are not stable identifiers.

For a candidate data object, run the lightweight local validator:

```text
validate_osm_data(
  data={
    "lat": 40.1811,
    "lon": 44.5131,
    "tags": {
      "amenity": "cafe",
      "outdoor_seating": "yes"
    }
  }
)
```

Validation is advisory. Confirm tags against the OSM Wiki, Taginfo, local
mapping practice, and permitted evidence.

## Writes are deliberately separate

The safe profile does not register natural-language create, update, delete, or
batch-write tools. A conversational “yes” is not write confirmation.

For surveyed road geometry, use the `review_gpx_road_edit` prompt. It requires
an explicit segment, explicit create/update decision, exact target way IDs for
updates, a non-writing preview, and review of the complete proposal digest. A
later production apply also requires a separate MCP host elicitation bound to
that same digest.

Other feature-edit workflows are outside the supported 0.2.0 safe surface. Use
an established OSM editor when the server cannot produce a reviewable proposal.

## Review checklist

- Verify the parser did not invent a name, address, source, or feature type.
- Search for existing objects before proposing a duplicate.
- Use current OSM tags and respect regional conventions.
- Never derive geometry from prohibited imagery or routing output.
- Keep private GPX data local; do not paste it into public issue reports.
- Stop when the target object or evidence is ambiguous.

Reference material:

- [OSM good practice](https://wiki.openstreetmap.org/wiki/Good_practice)
- [OSM map features](https://wiki.openstreetmap.org/wiki/Map_features)
- [Taginfo](https://taginfo.openstreetmap.org/)
