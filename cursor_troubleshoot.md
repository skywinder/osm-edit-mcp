# Cursor MCP Integration Troubleshooting

## Issue: no tools or prompts appear in Cursor

### 1. Use the released package entry point

Configure Cursor with the package command, without checkout-specific path or
environment overrides:

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

The first launch may take longer while `uvx` creates an isolated environment.

### 2. Test `uvx` outside Cursor

```bash
uvx --version
npx -y @modelcontextprotocol/inspector uvx osm-edit-mcp
```

If `uvx` works in a terminal but Cursor cannot find it, run `command -v uvx`
and use that absolute executable path as the configuration's `command` value.
Keep the package entry point as the single argument instead of invoking a source
file directly.

### 3. Test unreleased changes from a local checkout

Install exactly the dependencies recorded in `uv.lock`:

```bash
cd /absolute/path/to/osm-edit-mcp
uv sync --locked --extra dev
npx -y @modelcontextprotocol/inspector uv run --locked osm-edit-mcp
```

For Cursor to launch that checkout, use the console entry point through the
project environment:

```json
{
  "mcpServers": {
    "osm-edit-local": {
      "command": "uv",
      "args": [
        "run",
        "--locked",
        "--project",
        "/absolute/path/to/osm-edit-mcp",
        "osm-edit-mcp"
      ],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_REQUIRE_HOST_CONFIRMATION": "true"
      }
    }
  }
}
```

### 4. Check Cursor MCP logs

1. Open **View → Output** and select **MCP**.
2. Fully quit and restart Cursor after changing the configuration.
3. Look for command-not-found, package-resolution, JSON, or startup errors.
4. Confirm the configured server is enabled and its tool and prompt lists are
   populated.

### 5. Run the repository debug helper

From a synced local checkout:

```bash
uv run --locked python debug_mcp_cursor.py
```

Share the helper output and the relevant Cursor MCP log entries if the server
still fails to initialize. Remove credentials and tokens before sharing logs.
