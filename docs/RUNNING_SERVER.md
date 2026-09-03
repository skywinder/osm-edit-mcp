# Running the server

OSM Edit MCP is a local stdio server. In normal use, the MCP host launches it
as a child process and exchanges JSON-RPC messages over stdin/stdout.

## Recommended command

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

The host starts the server when needed and stops it when the session ends. Do
not run it under `nohup`, systemd, tmux, PM2, or another background manager:
those tools do not provide the MCP stdio connection expected by the client.

## Inspect the protocol manually

Use the official MCP Inspector when debugging outside a host:

```bash
npx -y @modelcontextprotocol/inspector uvx osm-edit-mcp
```

The Inspector owns the stdio process and provides a UI for initialization,
`tools/list`, and safe tool calls. Start with `get_server_info`.

## Source checkout

Contributors can point a host or Inspector at an existing checkout:

```bash
uv sync --locked --extra dev
npx -y @modelcontextprotocol/inspector uv run --locked osm-edit-mcp
```

Keep `OSM_USE_DEV_API=true` for all development and acceptance work.

## Logs and lifecycle

- Server diagnostics are written to stderr so they do not corrupt MCP stdout.
- View logs in the MCP host's server/output panel.
- A process that exits is normally restarted by the host on reconnect.
- There is no normal MCP listening port or HTTP health endpoint.

The repository retains a legacy read-only HTTP wrapper for compatibility, but
it is not the proposal-based write transport and is not part of the package
quick start.

See [MCP client setup](MCP_CLIENT_SETUP.md) for configuration formats and
[troubleshooting](MCP_TROUBLESHOOTING.md) for connection failures.
