# OSM Edit MCP

[![MCP Badge](https://lobehub.com/badge/mcp/pk-osm-edit-mcp)](https://lobehub.com/mcp/pk-osm-edit-mcp)
[![PyPI](https://img.shields.io/pypi/v/osm-edit-mcp.svg)](https://pypi.org/project/osm-edit-mcp/)
[![CI](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/osm-edit-mcp.svg)](https://pypi.org/project/osm-edit-mcp/)
[![License](https://img.shields.io/pypi/l/osm-edit-mcp.svg)](LICENSE)

A review-first Model Context Protocol server for inspecting OpenStreetMap and
turning a selected part of a local GPX survey into a previewed road-edit proposal.

> **Alpha software.** It does not autonomously edit OpenStreetMap. The normal
> profile can inspect data and prepare proposals, but a production write requires
> an exact preview, a separate MCP host confirmation of its SHA-256 digest, fresh
> OSM identity/version checks, and one atomic `osmChange` upload.

## Why this server

Most OpenStreetMap MCP servers focus on search, geocoding, or routing. OSM Edit
MCP focuses on the risky last mile: helping a mapper review a narrowly selected
survey before any road geometry reaches OSM.

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

Use `search_nearby_places` for museums, parks, viewpoints, useful amenities and
exact OSM tag combinations. It searches nodes, ways and relations, returns stable
OSM links and explicitly **straight-line** distances, then deduplicates/sorts/limits
with `total`, `count` and `truncated`. No OAuth is needed.

```json
{"lat":40.197784,"lon":44.51098,"radius_meters":1200,"categories":["museum","park","viewpoint"],"limit":15}
```

`find_nearby_amenities` remains compatible (including `radius` alias).
`search_osm_elements` now requires a bounded bbox or lat/lon/radius; unscoped global
regex scans are no longer allowed. See [nearby search documentation](docs/NEARBY_SEARCH.md)
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

For client-specific formats, including Codex TOML, see
[MCP client setup](docs/MCP_CLIENT_SETUP.md). A real read-only protocol smoke
client is available at [examples/quick_start.py](examples/quick_start.py).

MCP hosts can also start the guided `review_gpx_road_edit` prompt with a local
GPX path and edit goal. It requires explicit segment and target choices, builds
a non-writing preview, and stops at review of the complete proposal digest. It
never calls `apply_osm_edit`.

## Review workflow

Keep private tracks outside the repository. Set `OSM_TRACK_IMPORT_DIR` to a
directory you control, or provide inline GPX XML. Files are limited to 10 MiB
and 100,000 raw points; path traversal and symlink escapes are rejected.

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

```text
match_track_selection(selection_id="<selection_id>", costing="auto")
suggest_track_road_candidates(selection_id="<selection_id>")
```

Valhalla output is diagnostic only. Candidate discovery never selects the target
way on the mapper's behalf.

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

The package quick start is intentionally safe for inspection. Production setup
is an advanced operator workflow:

1. Register separate development and production OAuth applications with only
   `read_prefs` and `write_api`.
2. From an existing source checkout, create a private `.env`, configure the
   development application, then authenticate it:

   ```bash
   install -m 600 .env.example .env
   uv sync --locked --extra dev
   export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
   uv run python oauth_auth.py --dev
   ```

3. Complete representative create/update preview and apply acceptance against
   the OSM development API.
4. Only after that development acceptance, configure and authenticate the
   separate production app:

   ```bash
   export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
   uv run python oauth_auth.py --prod
   ```

Tokens are keyring-first. Plaintext compatibility files are disabled by default
and, when explicitly enabled, must have mode `0600`.

Do not switch to `OSM_USE_DEV_API=false` unless
`get_edit_capabilities` reports the expected account, production target,
`safe` profile, and digest-bound host confirmation.

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

- [Quick start](docs/quick-start-guide.md)
- [MCP client setup](docs/MCP_CLIENT_SETUP.md)
- [Safe usage examples](docs/mcp-usage-examples.md)
- [Troubleshooting](docs/MCP_TROUBLESHOOTING.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT. OpenStreetMap edits are also subject to the OSM contributor terms,
community guidelines, and source-licensing requirements.
