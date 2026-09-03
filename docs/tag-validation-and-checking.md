# Tag validation and checking

The 0.2.0 MCP surface provides one lightweight validator:
`validate_osm_data`. It is read-only and does not contact OSM to approve or
upload an edit.

## Input

Pass coordinates and/or a `tags` object:

```text
validate_osm_data(
  data={
    "lat": 40.1811,
    "lon": 44.5131,
    "tags": {
      "amenity": "restaurant",
      "cuisine": "armenian",
      "name": "Example name to verify"
    }
  }
)
```

The tool checks:

- latitude and longitude ranges;
- suspicious coordinates near `(0, 0)`;
- empty tag keys or values and `=` in keys;
- very long values;
- a small set of common tag conflicts and missing complementary tags;
- a basic `opening_hours` shape hint.

## Output

On success, `data` contains:

- `issues`: blocking local validation findings;
- `warnings`: conditions requiring review;
- `suggestions`: optional improvements;
- `is_valid`: true only when no local issues were found;
- `validation_score` and `quality_grade`: heuristic summaries.

An A grade is not proof that the data is correct, current, licensed, or ready
for upload. The validator does not implement the full OSM tagging model and does
not query Taginfo or the OSM Wiki.

## Checks outside this tool

Before any proposed edit:

1. Read the current OSM object, tags, geometry, and version.
2. Search for duplicates and nearby related objects.
3. Verify candidate tags in the OSM Wiki and Taginfo.
4. Check evidence provenance and applicable import/automated-edit policy.
5. For GPX road geometry, inspect the complete proposal preview, topology, and
   digest produced by `preview_track_road_edit`.
6. Stop if evidence, identity, API target, or exact element selection is
   ambiguous.

There are no registered MCP tools for batch tag operations, generic tag merges,
tag documentation lookup, related-tag discovery, or natural-language writes in
the safe profile. Do not invent those calls.

Useful references:

- [OSM good practice](https://wiki.openstreetmap.org/wiki/Good_practice)
- [OSM map features](https://wiki.openstreetmap.org/wiki/Map_features)
- [Taginfo](https://taginfo.openstreetmap.org/)
