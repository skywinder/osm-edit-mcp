# Safe MCP usage examples

These examples assume the released server is configured with:

```json
{
  "command": "uvx",
  "args": ["osm-edit-mcp"],
  "env": {
    "OSM_USE_DEV_API": "true",
    "OSM_WRITE_PROFILE": "safe"
  }
}
```

OSM Edit MCP is review-first. Natural language can help describe an intent, but
it cannot select an ambiguous OSM object or authorize a production write.
Inspection, GPX analysis, and the selected-segment preview need no credentials.
The edit-proposal examples below assume a completed development OAuth flow:
`preview_track_road_edit` does not write, but it binds its proposal to the
verified OSM account and API target.

## Confirm the environment

```text
get_edit_capabilities()
```

Before doing anything else, verify that the result reports:

- `environment: development`;
- `write_profile: safe`;
- raw write tools are not registered;
- production confirmation uses MCP elicitation bound to a proposal digest.

## Inspect a small map area

```text
inspect_map_context(
  bbox="-0.1280,51.5068,-0.1268,51.5078",
  highway_only=true,
  max_elements=500
)
```

This returns stable IDs, versions, tags, and GeoJSON. It does not create a
proposal or changeset.

## Analyze a local GPX

```text
analyze_gpx_track(gpx_path="survey.gpx")
```

Review the returned segments, point counts, times, bounds, distance, and
discontinuity warnings. Do not join distinct recording segments.

For a long history export, select only the part supported by your survey:

```text
create_track_selection(
  track_id="<track_id>",
  segment_id="trk-0-seg-0",
  start_point_index=1240,
  end_point_index=1395
)
```

Open `preview_uri` when supported, or inspect the GeoJSON fallback.

## Compare without choosing a target automatically

```text
match_track_selection(
  selection_id="<selection_id>",
  costing="auto"
)
```

```text
suggest_track_road_candidates(
  selection_id="<selection_id>"
)
```

Map matching is optional and diagnostic. Candidate suggestions provide evidence
for the mapper; they do not choose a way automatically.

## Preview a new road

```text
preview_track_road_edit(
  selection_id="<selection_id>",
  action="create",
  tags={"highway":"residential"},
  changeset_comment="Add surveyed residential road",
  changeset_source="survey",
  evidence_kind="survey_gpx"
)
```

This is a non-writing operation. Review:

- `current_geojson` and `proposed_geojson`;
- exact node/way operations and public tags;
- endpoint snaps, connections, and dangling endpoints;
- crossings and topology warnings;
- blocking issues, API target, expiry, and `proposal_digest`.

## Preview an existing road chain

Choose explicit, ordered, contiguous way IDs:

```text
preview_track_road_edit(
  selection_id="<selection_id>",
  action="update",
  target_way_ids=[123456, 123457],
  changeset_comment="Realign road from local survey",
  changeset_source="survey",
  evidence_kind="survey_gpx"
)
```

The planner preserves each way ID and tag set, plus shared, tagged,
relation-member, anchor, and chain-boundary nodes. A protected node too far from
the surveyed alignment blocks the proposal.

## Apply only the reviewed digest

```text
apply_osm_edit(
  proposal_id="<proposal_id>",
  proposal_digest="<exact_sha256_from_preview>"
)
```

Against production, the MCP host must present a separate confirmation request
for this exact digest. The server then re-verifies the API target, OSM account,
`write_api` permission, referenced versions, and affected highways.

Do not translate a conversational “yes” into a raw write call. If the host does
not support elicitation, production apply must remain unavailable.

## Verify an applied proposal

```text
verify_osm_edit(proposal_id="<proposal_id>")
```

```text
list_edit_proposals(status="APPLIED")
```

The apply receipt contains the changeset link, element IDs and versions, close
status, and post-write verification. A `RECONCILE_REQUIRED` result means the
upload outcome is ambiguous and must be inspected; it must not be blindly
retried.

## Read-only protocol smoke

[examples/quick_start.py](../examples/quick_start.py) starts the released server
over stdio, completes MCP initialization, verifies the read-only annotation on
`get_server_info`, and calls only that tool.

From an existing source checkout:

```bash
uv run python examples/quick_start.py
```

The example performs no OSM network write, OAuth flow, or changeset operation.
