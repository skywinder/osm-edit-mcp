# OSM tagging with the 0.2.0 safe profile

Tags are public map data. This server can suggest and locally validate candidate
tags, but it does not replace the OSM Wiki, Taginfo, local knowledge, or human
review.

## Registered tagging helpers

`parse_natural_language_osm_request` converts a description into a heuristic
interpretation and candidate tags:

```text
parse_natural_language_osm_request(
  request="Find a wheelchair-accessible pharmacy"
)
```

`validate_osm_data` checks basic coordinate bounds, empty keys/values, a few
common conflicts, and simple quality suggestions:

```text
validate_osm_data(
  data={
    "lat": 51.5074,
    "lon": -0.1278,
    "tags": {
      "amenity": "pharmacy",
      "wheelchair": "yes"
    }
  }
)
```

The validation score is a local heuristic, not approval to upload. The server
does not expose tools named `validate_tags`, `explain_tags`, batch tagging, or a
natural-language feature creator.

## Candidate tag examples

These are data illustrations, not edit instructions:

| Observed feature | Candidate tags to review |
|---|---|
| Cafe | `amenity=cafe` |
| Restaurant | `amenity=restaurant` plus a verified `cuisine=*` when known |
| Pharmacy | `amenity=pharmacy` |
| Supermarket | `shop=supermarket` |
| Public library | `amenity=library` |
| Residential road | `highway=residential` only when survey and local context support it |

Names, opening hours, accessibility, contact information, and addresses must be
based on current, permitted evidence. Do not infer them from a business type.

## Road-geometry proposals

For a local GPX survey, use the review-first sequence:

```text
analyze_gpx_track → create_track_selection
  → suggest_track_road_candidates → preview_track_road_edit
```

`preview_track_road_edit` is non-writing but requires an authenticated OSM
identity so the proposal is bound to the exact account and API target. Review
all tags, topology, element operations, warnings, blocking issues, and the full
`proposal_digest`. The `review_gpx_road_edit` prompt stops at this point and
does not call apply.

## Tag review checklist

- Check the current OSM object and version before proposing a change.
- Prefer the most specific established tag supported by evidence.
- Preserve existing tags unless the proposal explains why they change.
- Do not combine unrelated features merely to fit one object.
- Check lifecycle prefixes such as `disused:*` against current OSM practice.
- Verify `opening_hours` with a dedicated validator when the value is complex.
- Avoid copying copyrighted or prohibited map sources.

Current references:

- [OSM map features](https://wiki.openstreetmap.org/wiki/Map_features)
- [OSM tagging good practice](https://wiki.openstreetmap.org/wiki/Good_practice)
- [Taginfo](https://taginfo.openstreetmap.org/)
- [OSM opening hours](https://wiki.openstreetmap.org/wiki/Key:opening_hours)
