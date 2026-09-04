# MCP client setup

OSM Edit MCP uses the standard local stdio transport. The MCP host owns the
server process and should launch the released package with `uvx`.

## Requirements

- Python 3.10 or newer;
- [uv](https://docs.astral.sh/uv/) with `uvx` available to the host;
- an MCP client that supports local stdio servers;
- MCP elicitation support for production `apply_osm_edit`.

The examples below force the OSM development API and the `safe` profile.

## JSON-based clients

Claude Desktop, Cursor, Cline, and many other hosts accept this shape:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_REQUIRE_HOST_CONFIRMATION": "true"
      }
    }
  }
}
```

If the client uses a different outer key, keep the server command, arguments,
and environment unchanged. Restart the client after editing its configuration.

## Codex

Add this to the Codex configuration:

```toml
[mcp_servers.osm_edit]
command = "uvx"
args = ["osm-edit-mcp"]

[mcp_servers.osm_edit.env]
OSM_USE_DEV_API = "true"
OSM_WRITE_PROFILE = "safe"
OSM_REQUIRE_HOST_CONFIRMATION = "true"
```

## Hermes Agent

Hermes users can install the repository's
[setup skill](../skills/osm-edit-mcp-setup/SKILL.md) and let the agent
perform the guarded procedure, or configure the stdio server directly. OAuth
bootstrap currently requires a source checkout, so this example launches that
checkout with its locked environment:

```bash
hermes mcp add osm-edit \
  --command /absolute/path/to/uv \
  --connect-timeout 120 \
  --env \
    OSM_EDIT_MCP_ENV_FILE=/absolute/path/to/osm-edit-mcp.env \
    XDG_DATA_HOME=/absolute/path/to/persistent-keyring-data \
    OSM_WRITE_PROFILE=safe \
    OSM_REQUIRE_HOST_CONFIRMATION=true \
  --args run --locked --project /absolute/path/to/osm-edit-mcp osm-edit-mcp
```

`hermes mcp add` performs discovery and then asks which tools to enable. In an
agent-driven session, run it with a PTY and answer that selection prompt; a
non-interactive EOF prints `Cancelled` and does not save the server even when
the preceding connection and tool discovery succeeded. Confirm persistence with
`hermes mcp test osm-edit` after the add process exits.

Use the same `XDG_DATA_HOME` when running `oauth_auth.py`, otherwise the helper
can save a valid token in one keyring namespace while the MCP subprocess reads
another. Prefer the platform keyring. If a headless deployment explicitly uses
`keyrings.alt.file.PlaintextKeyring`, install `keyrings.alt` in the same runtime,
pass `PYTHON_KEYRING_BACKEND` to both processes, and protect its persistent
directory; that fallback is not encrypted secret storage.

Keep OAuth client credentials and the API selector in the private env file,
which must be a regular, non-symlink file with mode `0600`:

```dotenv
OSM_USE_DEV_API=true
OSM_DEV_CLIENT_ID=<development-client-id>
OSM_DEV_CLIENT_SECRET=<development-client-secret>
OSM_DEV_REDIRECT_URI=https://localhost:8080/callback
OSM_WRITE_PROFILE=safe
OSM_REQUIRE_HOST_CONFIRMATION=true
```

Do not duplicate `OSM_USE_DEV_API` under the Hermes server's `env` mapping when
`OSM_EDIT_MCP_ENV_FILE` already provides it. In particular, using
`hermes config set` on an unknown nested environment key may coerce `false` to a
YAML boolean, while MCP stdio process environments require strings. Trying to
preserve it with shell quotes can instead store the quote characters. Either
mismatch can close the MCP connection during Pydantic startup validation.
Remove a duplicate selector with:

```bash
hermes config unset mcp_servers.osm-edit.env.OSM_USE_DEV_API
```

Then verify the fresh process before restarting the active Hermes runtime:

```bash
hermes mcp test osm-edit
```

After reconnection, call `get_edit_capabilities` and `check_authentication`.
Confirm the API target, `safe` profile, expected OSM account, and `write_api`
permission together. A successful standalone OAuth flow does not prove that an
already-running MCP subprocess has reloaded its environment.

## Local GPX files

The server accepts inline GPX XML or paths below `OSM_TRACK_IMPORT_DIR`.
Prefer an explicit directory outside the repository:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_TRACK_IMPORT_DIR": "/absolute/path/to/local-gpx"
      }
    }
  }
}
```

The path must be absolute from the host process's point of view. Track files are
limited by configured size and point-count caps, and path traversal or symlink
escapes are rejected.

## Separate development and production entries

Do not reuse an OAuth application or configuration entry across environments.
After completing development-API acceptance, a production-capable host can use:

```json
{
  "mcpServers": {
    "osm-edit-dev": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe"
      }
    },
    "osm-edit-prod": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "false",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_REQUIRE_HOST_CONFIRMATION": "true"
      }
    }
  }
}
```

Keep the production entry disabled until:

1. A separate production OAuth app has been registered.
2. The expected account and `write_api` permission are verified live.
3. The host is known to implement MCP elicitation.
4. `get_edit_capabilities` reports the production API, `safe` profile, and
   digest-bound confirmation.

If the host does not support elicitation, production apply must fail closed.

## Development from a source checkout

Contributors can run the current checkout instead of the released package:

```bash
uv sync --locked --extra dev
```

Then point the host at that checkout:

```json
{
  "mcpServers": {
    "osm-edit-source": {
      "command": "uv",
      "args": [
        "run",
        "--locked",
        "--project",
        "/absolute/path/to/checkout",
        "osm-edit-mcp"
      ],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe"
      }
    }
  }
}
```

Source checkout mode is also currently required for the OAuth bootstrap script:

```bash
install -m 600 .env.example .env
export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
uv run python oauth_auth.py --dev
```

Do not authenticate against production until representative development-server
create and update acceptance has succeeded.

## Verify the connection

After reconnecting:

1. Call `get_server_info`.
2. Call `get_edit_capabilities`.
3. Confirm the API target and write profile.
4. Inspect the tool list: raw direct-write tools must be absent in `safe`.
5. Optionally run the real read-only client in
   [examples/quick_start.py](../examples/quick_start.py).

## Host limitations

- A client that cannot open `ui://` resources can still inspect the returned
  GeoJSON.
- A client that cannot perform elicitation can preview proposals but cannot
  apply them to production.
- The server communicates over stdio. Do not configure a TCP port, daemon, or
  HTTP URL for the normal MCP transport.

See [troubleshooting](MCP_TROUBLESHOOTING.md) if the process exits or tools do
not appear.
