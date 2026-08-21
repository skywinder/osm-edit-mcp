# OSM Edit MCP

A local Model Context Protocol server for inspecting OpenStreetMap and turning a
selected part of a GPX survey into reviewed OSM road geometry.

The default profile is deliberately narrow: an agent may inspect data and build
previews, but a production write can happen only through a persistent proposal,
a separate MCP host confirmation, fresh OSM version/permission checks, and one
atomic `osmChange` upload.

## What is supported

- Read OSM nodes, ways, relations, changesets, and small map areas.
- Analyze GPX 1.0/1.1 without uploading the trace to OSM.
- Crop one continuous range by point indexes, timestamps, or endpoint coordinates.
- Run optional map matching against a local Valhalla instance.
- Suggest nearby `highway=*` ways without selecting one automatically.
- Preview a new road or reshape a selected contiguous chain of existing ways.
- Display current/proposed GeoJSON through `ui://` MCP preview resources.
- Apply one reviewed proposal atomically and return real OSM IDs, versions, and links.
- Re-fetch an applied edit for verification.

This release does not publish GPS traces, infer at-grade crossings, delete roads,
restructure relations, or copy geometry from restricted map providers.

## Safety model

The normal `safe` profile enforces the following:

1. A preview contains the exact node/way operations, tags, warnings, topology
   decisions, API target, expiry, and a SHA-256 digest.
2. Proposals live in a local SQLite state machine and are atomically claimed.
   Concurrent or repeated apply calls cannot upload the same proposal twice.
3. Production `apply_osm_edit` asks the MCP host to confirm the exact digest.
   The old `confirm=true` endpoint refuses production writes.
4. Apply verifies the live OAuth identity and `write_api` permission, binds the
   proposal to the API/account, and re-fetches every referenced OSM version.
5. All creates, way modifications, and `if-unused` cleanup are sent in one
   transactional `POST /changeset/{id}/upload`.
6. A network failure after upload begins is marked `RECONCILE_REQUIRED`; the
   server never retries an ambiguous upload blindly.
7. Raw node/way and natural-language direct-write tools are not registered in
   the safe profile. They can only be exposed with `OSM_WRITE_PROFILE=expert`
   while targeting the development API.

A GPS trace can be offset or noisy. Always review it against independent,
permitted evidence. Personal labels and private location history do not belong
in public OSM tags.

## Install

Requirements: Python 3.10+ and an MCP host that supports stdio. MCP elicitation
support is required for production apply.

```bash
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
uv sync --dev
cp .env.example .env
```

The example configuration targets the OSM development server. Keep
`OSM_USE_DEV_API=true` until the entire workflow has been tested there.

## OAuth

Register separate OAuth applications for development and production. Grant only:

- `read_prefs`
- `write_api`

Put the corresponding client ID, client secret, and loopback redirect URI in
`.env`, then authenticate:

```bash
uv run python oauth_auth.py --dev
# production, only after dev acceptance:
uv run python oauth_auth.py --prod
```

OAuth uses PKCE and a random validated state. Tokens are stored in the operating
system keyring. Plaintext `.osm_token_*.json` files are ignored unless the
explicit compatibility setting is enabled and the file mode is `0600`.

## Connect an MCP host

Use an absolute repository path. A typical stdio configuration is:

```json
{
  "mcpServers": {
    "osm-edit-dev": {
      "command": "uv",
      "args": ["run", "osm-edit-mcp"],
      "cwd": "/absolute/path/to/osm-edit-mcp",
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe"
      }
    }
  }
}
```

Create a separate production entry; do not reuse the dev OAuth application:

```json
{
  "mcpServers": {
    "osm-edit-prod": {
      "command": "uv",
      "args": ["run", "osm-edit-mcp"],
      "cwd": "/absolute/path/to/osm-edit-mcp",
      "env": {
        "OSM_USE_DEV_API": "false",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_REQUIRE_HOST_CONFIRMATION": "true"
      }
    }
  }
}
```

After reconnecting, call `get_edit_capabilities`. Check the environment, API
target, live verified OAuth account/permissions, write profile, confirmation
mechanism, and Valhalla status before asking the agent to edit anything.

See [MCP client setup](docs/MCP_CLIENT_SETUP.md) for client-specific locations.

## GPX road workflow

Put a GPX file below `OSM_TRACK_IMPORT_DIR` (default `./tracks`) or pass inline
XML. Path traversal and symlink escapes are rejected. Files are capped at 10 MiB
and 100,000 raw points.

### 1. Analyze

```text
analyze_gpx_track(gpx_path="survey.gpx")
```

The result returns `track_id`, stable segment IDs, point counts, times, bounds,
distance, and discontinuity warnings. Separate recording segments are never joined.

### 2. Select only the surveyed road

For a long history, keep the raw GPX local and select a short continuous range:

```text
create_track_selection(
  track_id="<track_id>",
  segment_id="trk-0-seg-0",
  start_point_index=1240,
  end_point_index=1395
)
```

Timestamp and start/end-coordinate selection are also supported. Open the returned
`preview_uri` if the MCP host supports resource previews; GeoJSON is always included
as a fallback.

### 3. Compare with current roads

```text
match_track_selection(selection_id="<selection_id>", costing="auto")
suggest_track_road_candidates(selection_id="<selection_id>")
```

Valhalla output is diagnostic only. It identifies likely already-mapped and
unmatched spans but is never copied into OSM geometry.

### 4. Preview

Create a new road with explicit classification:

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

Or reshape an explicitly selected, ordered, contiguous chain:

```text
preview_track_road_edit(
  selection_id="<selection_id>",
  action="update",
  target_way_ids=[123456, 123457],
  changeset_comment="Realign road from GPS survey",
  changeset_source="survey",
  evidence_kind="survey_gpx"
)
```

Updates preserve each existing way ID and its full tag set. Shared, tagged,
relation-member, anchor, and chain-boundary nodes are preserved. A protected node
more than the alignment tolerance from the survey blocks the proposal.

For new roads, endpoints may reuse a nearby highway node or insert one shared node
into exactly one unambiguous nearby way. The planner blocks ambiguous nodes/ways and
incompatible `layer`, `bridge`, or `tunnel` connections. It reports dangling
endpoints and interior crossings instead of inventing connectivity.

Review all of these fields:

- `preview_uri`, `current_geojson`, and `proposed_geojson`
- exact `operations` and public tags
- `endpoint_snaps`, `endpoint_way_connections`, and `dangling_endpoints`
- `preserved_nodes` and conditional deletions
- warnings, blocking issues, API target, expiry, and `proposal_digest`

### 5. Apply through the host

Pass the exact returned ID and digest to `apply_osm_edit`. The MCP host must show a
separate confirmation request for that digest. The apply result includes a public
changeset link, element links, real IDs/versions, close status, and post-write
verification.

The compatibility tool `apply_track_road_edit(confirm=true)` remains usable against
the development API for older clients. It cannot publish to production when host
confirmation is required.

### 6. Verify later

```text
verify_osm_edit(proposal_id="<proposal_id>")
list_edit_proposals(status="APPLIED")
```

## Local Valhalla

Set `OSM_VALHALLA_URL` to a Valhalla service bound to loopback, normally
`http://127.0.0.1:8002`. Remote hostnames are rejected so a private GPX is not sent
to a third party. Build Valhalla tiles from an appropriately licensed regional OSM
extract, then confirm availability with `get_edit_capabilities`.

Map matching is optional; candidate suggestion and manual preview still work without it.

## Tool groups

Safe editing and review:

- `get_edit_capabilities`
- `inspect_map_context`
- `analyze_gpx_track`
- `create_track_selection`
- `match_track_selection`
- `suggest_track_road_candidates`
- `preview_track_road_edit`
- `apply_osm_edit`
- `list_edit_proposals`
- `verify_osm_edit`

The existing read/search/validation tools remain available. The parser may turn
natural language into a suggested intent, but it does not receive production write
authority and must not choose an ambiguous OSM object by itself.

## Production checklist

Before changing `OSM_USE_DEV_API=false`:

1. Complete create and partial multi-way update acceptance on the dev API.
2. Confirm `get_edit_capabilities` reports `safe`, production confirmation, and
   the expected account/API target.
3. Review the exact GPX subsection locally; do not send an entire private history.
4. Use only your own survey, local knowledge, or imagery permitted for OSM tracing.
   Permitted imagery must be explicitly listed in
   `OSM_PERMITTED_IMAGERY_SOURCES`; Yandex and Google geometry are rejected.
5. Open the proposal map and exact operations before approving.

## Tests

Unit tests are network-mocked and force the development API at import time:

```bash
uv run pytest
uv run pytest --cov=src/osm_edit_mcp --cov-report=term-missing
```

Development-API acceptance is intentionally opt-in and must never be pointed at
production. It should analyze a representative GPX, create a road, reshape a partial
multi-way chain, then verify IDs, tags, intersections, versions, and changeset history.

## Legacy HTTP wrapper

`web_server.py` is not the write transport. It binds to loopback by default, refuses
startup without an explicit API key, uses an exact CORS allowlist, and all former
direct-write routes return HTTP 410. Use stdio MCP for proposal-based edits.

## License

MIT. OSM edits are also subject to OpenStreetMap contributor terms, mapping
guidelines, and source licensing requirements.
