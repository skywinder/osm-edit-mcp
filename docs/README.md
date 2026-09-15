# OSM Edit MCP: detailed guide

For the shortest installation path, see the [main README](../README.md).
This guide covers GPX examples, editing requirements, safety and development.

- [GPX workflow](#review-workflow), including a [credential-free example](#try-a-local-preview-without-oauth-or-valhalla)
- [OAuth and production](#oauth-and-production-use)
- [Client configuration](MCP_CLIENT_SETUP.md) and [Hermes](HERMES_SETUP.md)
- [Nearby search](NEARBY_SEARCH.md), [Valhalla](VALHALLA.md), and [troubleshooting](MCP_TROUBLESHOOTING.md)
- [Server lifecycle and Inspector](RUNNING_SERVER.md)

## Why this server

Use public place discovery without OAuth, or the separate review-first editing
workflow to inspect a selected survey before road geometry reaches OSM.

```text
local GPX → selected segment → current/proposed preview
          → exact digest confirmation → OSM changeset
```

The safe profile can:

- read OSM nodes, ways, relations, changesets, and small map areas;
- analyze GPX 1.0/1.1 locally without publishing the trace;
- select one continuous range by index, time, or endpoint coordinates;
- optionally compare it with local Valhalla map matching;
- suggest nearby `highway=*` ways without choosing one automatically;
- preview a new road or a selected contiguous chain of existing ways;
- expose current/proposed GeoJSON through an MCP `ui://` resource;
- apply one confirmed proposal atomically and return OSM links and versions;
- re-fetch a completed edit for later verification.

It does **not** upload GPS traces, infer crossings, delete roads, restructure
relations, copy geometry from restricted providers, or authorize a production
edit from natural-language consent alone.

## Read-only nearby discovery

**Available from version 0.2.2.** Set `OSM_TOOL_PROFILE=discovery` to expose only three client-neutral
tools: `resolve_location`, `search_nearby_places`, and `get_place_details`.

Use `search_nearby_places` for museums, parks, viewpoints, useful amenities and
exact OSM tag combinations. It searches nodes, ways and relations, returns stable
OSM links and explicitly **straight-line** distances, then deduplicates/sorts/limits
with `total`, `count` and `truncated`. Optional preferences explain why a place
ranks higher; unknown properties and opening hours remain explicit. No OAuth is
needed. The default `full` profile retains the editing workflow.

```json
{"lat":40.197784,"lon":44.51098,"radius_meters":1200,"categories":["museum","park","viewpoint"],"limit":15}
```

`find_nearby_amenities` remains compatible (including `radius` alias).
`search_osm_elements` now requires a bounded bbox or lat/lon/radius; unscoped global
regex scans are no longer allowed. See [nearby search documentation](NEARBY_SEARCH.md)
for categories, exact filters, distance caveats, migration examples and transport bounds.

## Quick start

Requirements:

- Python 3.10 or newer;
- [uv](https://docs.astral.sh/uv/);
- an MCP host that supports local stdio servers.

Recommended installation from [PyPI](https://pypi.org/project/osm-edit-mcp/):

```bash
uvx osm-edit-mcp
```

This command starts the stdio server and waits for an MCP client. For normal
use, put the same command in a JSON-based MCP host configuration:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe"
      }
    }
  }
}
```

Restart the host, then call `get_server_info` or `get_edit_capabilities`.
The first `uvx` launch installs the released package in an isolated environment.
The development API is the default in this example; no OAuth credentials are
needed for read-only inspection.

For client configuration and source-checkout setup, see
[MCP client setup](MCP_CLIENT_SETUP.md). A real read-only protocol smoke
client is available at [examples/quick_start.py](../examples/quick_start.py).

### Agent-assisted setup

The client-neutral [setup skill](../skills/osm-edit-mcp-setup/SKILL.md) guides an
agent through discovery or editing setup, preserving existing configuration and
verifying the selected profile. Place discovery needs no OAuth. Editing setup
checks the live API target, account and permissions without authorizing an edit.
See [MCP client setup](MCP_CLIENT_SETUP.md) for the functional diagnostic
helper and [Hermes setup](HERMES_SETUP.md) for Hermes-specific commands.

MCP hosts can also start the guided `review_gpx_road_edit` prompt with a local
GPX path and edit goal. It requires explicit segment and target choices, builds
a non-writing preview, and stops at review of the complete proposal digest. It
never calls `apply_osm_edit`.

## Review workflow

Keep private tracks outside the repository. Set `OSM_TRACK_IMPORT_DIR` to a
directory you control, or provide inline GPX XML. Files are limited to 10 MiB
and 100,000 raw points; path traversal and symlink escapes are rejected.

### Try a local preview without OAuth or Valhalla

Use the default `full` tool profile with `OSM_WRITE_PROFILE=safe`; the
`discovery`-only profile does not expose GPX tools. The calls below are MCP tool
calls, not shell commands. This synthetic track is only a connectivity example,
not survey evidence for a real OSM edit.

Call `analyze_gpx_track` with these JSON arguments:

```json
{"gpx_xml":"<gpx version=\"1.1\" xmlns=\"http://www.topografix.com/GPX/1/1\"><trk><trkseg><trkpt lat=\"40.1810\" lon=\"44.5130\"/><trkpt lat=\"40.1811\" lon=\"44.5131\"/><trkpt lat=\"40.1812\" lon=\"44.5132\"/></trkseg></trk></gpx>"}
```

Copy `data.track_id` from the result, then call `create_track_selection` in the
same server session, replacing the placeholder:

```json
{"track_id":"<returned track_id>","segment_id":"trk-0-seg-0","start_point_index":0,"end_point_index":2}
```

Read the returned `data.preview_uri` with the MCP client's `resources/read`, or
inspect the returned `data.geojson` if the host cannot display the resource.
Stop here: this previews the selected track, **not an OSM road-edit diff**. It
needs no OSM credentials, Valhalla service, or OSM API request. A road-edit
proposal in step 4 requires OAuth; applying it requires separate confirmation.

### 1. Analyze the track

```text
analyze_gpx_track(gpx_path="survey.gpx")
```

The result identifies stable track/segment IDs, bounds, distance, timestamps,
and discontinuities. Separate GPX segments are never joined implicitly.

### 2. Select only the surveyed section

```text
create_track_selection(
  track_id="<track_id>",
  segment_id="trk-0-seg-0",
  start_point_index=1240,
  end_point_index=1395
)
```

Timestamp and endpoint-coordinate selection are also supported. Review the
returned `preview_uri` or its GeoJSON fallback.

### 3. Compare with current OSM

Find candidates directly, including when Valhalla is not installed:

```text
suggest_track_road_candidates(selection_id="<selection_id>")
```

Optionally, with a local Valhalla service configured:

```text
match_track_selection(selection_id="<selection_id>", costing="auto")
```

Valhalla output is diagnostic only. Candidate discovery never selects the target
way on the mapper's behalf.

`match_track_selection` is optional and needs a **separate local Valhalla
service with routing tiles**. `uvx osm-edit-mcp` does not install it. If it is
unavailable, skip matching and continue with candidate discovery. See
[local Valhalla setup and diagnostics](VALHALLA.md).

Candidate discovery reads from the configured editing API. The development
sandbox is not a copy of the production map, so an empty result there does not
mean the real road is absent. Production object IDs/versions cannot be reused
as sandbox edit targets. Public place lookup can use the separate `discovery`
profile, which has no write tools; a mixed production-read/sandbox-write road
workflow is not supported.

Multiple traces can be inspected separately, but automatic multi-trace alignment,
consensus geometry, and cross-trace outlier rejection are not implemented.
Discontinuous-jump warnings on one trace are not a substitute for comparing
independent surveys. These limitations are tracked in [#7](https://github.com/skywinder/osm-edit-mcp/issues/7)
and [#10](https://github.com/skywinder/osm-edit-mcp/issues/10).

### 4. Build a non-writing preview

Track analysis, segment selection, and the selection preview work without OAuth.
`preview_track_road_edit` still requires an authenticated OSM identity because
the proposal is bound to that exact account and API target, even though this
step does not write to OSM.

For a new road:

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

For an existing contiguous chain:

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

Review the current/proposed GeoJSON, exact operations and tags, preserved nodes,
endpoint connections, warnings, blocking issues, API target, expiry, and
`proposal_digest`. Ambiguous topology is reported rather than invented.

### 5. Confirm and apply

`apply_osm_edit` accepts the exact proposal ID and digest. In production, the
MCP host must display a separate elicitation request for that digest. Apply then
checks the live OSM account, `write_api` permission, referenced versions, and
affected highways before sending one transactional upload.

A network failure after an upload starts becomes `RECONCILE_REQUIRED`; the
server does not blindly retry an ambiguous write.

### 6. Verify

```text
verify_osm_edit(proposal_id="<proposal_id>")
list_edit_proposals(status="APPLIED")
```

## Safety model

The normal `safe` profile enforces:

1. Exact, expiring proposals stored in a local SQLite state machine.
2. Atomic proposal claims that block concurrent or repeated upload.
3. API-target, account, permission, OSM-version, and content binding.
4. MCP elicitation bound to the proposal SHA-256 for production.
5. One transactional `osmChange` upload for creates and modifications.
6. Durable receipts and explicit reconciliation after ambiguous failures.
7. No registration of raw direct-write or natural-language write tools.

Raw write tools are available only in the explicit `expert` profile while
targeting the OSM development API.

GPX accuracy is not ground truth. Review every proposal against independent,
permitted evidence and local knowledge. Follow OpenStreetMap's mapping,
licensing, import, and automated-edit policies; systematic edits may require
community discussion even when this software requires per-proposal review.

## OAuth and production use

Road-edit preview binds a proposal to the verified OSM account and API target.
Apply rechecks the account, permissions and map versions before a confirmed upload.

Follow [editing authentication](MCP_CLIENT_SETUP.md#editing-authentication)
for separate development/production OAuth apps, private configuration files,
the source-only OAuth helper, keyring storage and live identity checks.
Do not overwrite an existing private configuration or send secrets/callbacks
through chat. The package does not implicitly load a copied `.env`.

Complete an explicitly authorized development edit and verify the MCP host's
confirmation support before configuring production. Production is not a shortcut
for an empty development-map result.

## Main tools

Inspection:

- `get_server_info`
- `get_edit_capabilities`
- `inspect_map_context`
- read/search/validation tools for OSM elements and tags

Review and editing:

- `analyze_gpx_track`
- `create_track_selection`
- `match_track_selection`
- `suggest_track_road_candidates`
- `preview_track_road_edit`
- `apply_osm_edit`
- `list_edit_proposals`
- `verify_osm_edit`

Guided prompt:

- `review_gpx_road_edit(gpx_path, edit_goal)`

## Development

For directory capability checks and the owner-update gate, see
[LobeHub listing maintenance](LOBEHUB.md).

From an existing source checkout:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest
uv run --locked --extra dev pytest --cov=src/osm_edit_mcp --cov-report=term-missing
```

Unit tests mock the network and force the development API at import time.
Development-API acceptance is separate and opt-in; it must never point at
production.

More documentation:

- [Quick start](quick-start-guide.md)
- [MCP client setup](MCP_CLIENT_SETUP.md)
- [Safe usage examples](mcp-usage-examples.md)
- [Troubleshooting](MCP_TROUBLESHOOTING.md)
- [Security policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)

## License

MIT. OpenStreetMap edits are also subject to the OSM contributor terms,
community guidelines, and source-licensing requirements.

## Mapping references

- [OSM tagging guide](osm-tagging-guide.md)
- [Tag validation guide](tag-validation-and-checking.md)
- [Natural-language parsing guide](natural-language-processing-guide.md)
- [OpenStreetMap Map Features](https://wiki.openstreetmap.org/wiki/Map_features)
- [Taginfo](https://taginfo.openstreetmap.org/)
- [OSM API 0.6](https://wiki.openstreetmap.org/wiki/API_v0.6)

Natural-language parsing suggests structured intent and tags. In the `safe`
profile it cannot select an ambiguous target, register raw write tools, or
replace the exact preview and digest-confirmation workflow.
