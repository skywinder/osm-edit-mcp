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
