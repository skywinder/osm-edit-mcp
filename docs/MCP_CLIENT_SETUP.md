# MCP client setup

OSM Edit MCP uses standard local stdio transport. The client owns the server
process. Python 3.10+ and [uv](https://docs.astral.sh/uv/) are required. There is
no server port or HTTP URL to configure. Use a host that supports MCP elicitation
before applying production edits.

## Choose a profile and package

- **Place discovery:** `OSM_TOOL_PROFILE=discovery` exposes only
  `resolve_location`, `search_nearby_places`, and `get_place_details`. No OAuth
  setup or development edit is required. These tools currently require a source
  checkout of the updated main branch; use a released package only once its
  release notes include them.
- **Editing and GPX:** the default `full` tool profile uses the `safe` write
  profile. The released package is launched with `uvx osm-edit-mcp`. OAuth is
  needed for authenticated operations, not public place discovery.

For a source checkout, run `uv sync --locked` in the checkout, then configure
this **inner server record** in the client's documented MCP configuration:

```json
{
  "command": "uv",
  "args": ["run", "--locked", "--project", "/absolute/path/to/checkout", "osm-edit-mcp"],
  "env": {"OSM_TOOL_PROFILE": "discovery"}
}
```

Some clients wrap this record inside `mcpServers` under a server name; others
use a different outer structure or a configuration UI. All `env` values must be
strings. Replace the executable with an absolute path if the host's PATH cannot
find it. Paths must exist inside the host's filesystem/container.

For released editing tools, use this inner record:

```json
{
  "command": "uvx",
  "args": ["osm-edit-mcp"],
  "env": {
    "OSM_USE_DEV_API": "true",
    "OSM_WRITE_PROFILE": "safe",
    "OSM_REQUIRE_HOST_CONFIRMATION": "true"
  }
}
```

For source editing, retain the source command/args and select
`OSM_TOOL_PROFILE=full`. Keep existing unrelated client settings. Reconnect the
server using the host's supported reload workflow; coordinate a restart when it
would interrupt an active session.

## Verify one fresh session

A successful initialization or tool list proves protocol connectivity, not
provider access or OAuth. Save the intended inner server record as a local JSON
file and run the source checkout's diagnostic helper:

```bash
uv run --locked --project /absolute/path/to/checkout python \
  /absolute/path/to/checkout/scripts/check_mcp_connection.py \
  --server-config /absolute/path/to/server.json --mode discovery
```

This verifies exactly three discovery tools. Add `--query "Matenadaran, Yerevan"`
to run resolve → nearby cafe/pharmacy search → details in that same session.
The probe sends the query and resolved coordinates to the configured public
providers. It requires a single location candidate and a nearby match; use a
precise public landmark if the location is ambiguous or empty. Respect provider
cooldowns rather than repeatedly running the probe after a failure.

The helper exits nonzero on failure and never edits OSM. It launches a separate
process: repeat a representative read through the active host to verify that
host's configuration. For discovery behavior and attribution, see
[nearby search](NEARBY_SEARCH.md).

## Editing authentication

Keep **separate development and production OAuth apps and server entries**.
Register the app on the selected OSM site, using the helper's callback URI
`https://localhost:8080/callback`, with `read_prefs` and `write_api` permissions.
Do not reuse development credentials for production.

Create a private, non-symlink dotenv file outside the checkout, with mode `0600`
on POSIX. Preserve existing credentials rather than overwriting a file. Use the
appropriate variables from [.env.example](../.env.example):

```dotenv
OSM_TOOL_PROFILE=full
OSM_USE_DEV_API=true
OSM_WRITE_PROFILE=safe
OSM_REQUIRE_HOST_CONFIRMATION=true
USE_KEYRING=true
ALLOW_PLAINTEXT_TOKEN_FILE=false
OSM_DEV_CLIENT_ID=<enter locally>
OSM_DEV_CLIENT_SECRET=<enter locally>
OSM_DEV_REDIRECT_URI=https://localhost:8080/callback
```

For a separate production file, set `OSM_USE_DEV_API=false` and use the
`OSM_PROD_CLIENT_ID`, `OSM_PROD_CLIENT_SECRET`, and `OSM_PROD_REDIRECT_URI` names.
Point each host entry at its file with string-valued
`OSM_EDIT_MCP_ENV_FILE=/absolute/path/to/private.env`. Remove duplicated profile
and API selectors from that entry's `env`; the process environment takes
precedence over the file. Do not put secrets in the server record.

The OAuth helper is currently source-only. Run it in your own local terminal
(or a verified user-visible terminal), using the same OS user, keyring backend,
and relevant XDG configuration as the MCP process:

```bash
OSM_EDIT_MCP_ENV_FILE=/absolute/path/to/private-dev.env \
  uv run --locked --project /absolute/path/to/checkout python \
  /absolute/path/to/checkout/oauth_auth.py --dev
```

For the separate production entry, use the production file and replace
`--dev` with `--prod`. The helper defaults to development; setting
`OSM_USE_DEV_API=false` alone does not select production in this helper. Enter credentials and callback URLs locally in the helper;
do not send them through chat, agent tool arguments, commits, or logs. An
agent's private PTY is not necessarily the visible integrated terminal. If the
keyring is unavailable, diagnose the selected backend instead of silently
enabling plaintext token storage.

Verify the intended account and environment in a fresh connection:

```bash
uv run --locked --project /absolute/path/to/checkout python \
  /absolute/path/to/checkout/scripts/check_mcp_connection.py \
  --server-config /absolute/path/to/dev-server.json --mode edit \
  --expect-environment development --expect-user YOUR_OSM_USERNAME
```

The helper calls `get_edit_capabilities` and `check_authentication` in one
session. It checks the canonical API URL, environment, expected username,
consistent live user ID, `write_api` permission, `safe` profile, absence of raw
write registration, and required digest-bound confirmation. It does not prove
that the host supports elicitation or that an edit has succeeded. Repeat these
checks through the active host after reloading it.

Before production apply, separately complete an authorized representative edit
on development and verify host elicitation support. Review the exact proposal
and digest. A host without elicitation can preview proposals; production apply
must fail closed. Connection setup does not authorize an OSM data change.

## GPX files and host limitations

Set `OSM_TRACK_IMPORT_DIR` to an explicit directory outside the repository for
local GPX input, or provide inline XML. Size/point caps apply; path traversal and
symlink escapes are rejected. The path is relative to the host's filesystem,
not the user's other computer. A host without `ui://` support can inspect the
returned GeoJSON.

See [troubleshooting](MCP_TROUBLESHOOTING.md), the client-neutral
[setup skill](../skills/osm-edit-mcp-setup/SKILL.md), and the separate
[Hermes guide](HERMES_SETUP.md).
