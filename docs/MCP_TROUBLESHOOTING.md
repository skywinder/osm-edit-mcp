# MCP troubleshooting

Start with the package-based development configuration:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_USE_DEV_API": "true",
        "OSM_WRITE_PROFILE": "safe",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Restart the MCP host after every configuration change.

## `uvx` is not found

Run `uvx --version` in a normal terminal. If it works there but not in the
host, the graphical application likely has a different PATH. Configure the
absolute path to the `uvx` executable as `command`, or launch the host from
an environment where uv is available.

## The package cannot be installed

Confirm network access and package availability:

```bash
uvx --refresh osm-edit-mcp
```

Remove no caches or credentials before recording the complete error. Package
resolution, Python compatibility, and a server protocol error are different
failure classes.

## The server exits during startup

Use the MCP Inspector to separate host configuration from server startup:

```bash
npx -y @modelcontextprotocol/inspector uvx osm-edit-mcp
```

Check stderr for a Python traceback. MCP stdout must contain protocol messages
only; wrappers that print banners to stdout will break initialization.

## No tools appear

1. Confirm the host completed MCP initialization.
2. Call `tools/list` in the Inspector.
3. Check that the configured command is `uvx` and the single argument is
   `osm-edit-mcp`.
4. Remove stale `cwd`, `PYTHONPATH`, and script-path settings left from an
   older source-checkout configuration.
5. Restart the host.

## The wrong tools appear

Call `get_edit_capabilities` and inspect `write_profile`. In the recommended
`safe` profile, raw direct-write tools are not registered.

If expert tools appear unexpectedly, remove `OSM_WRITE_PROFILE=expert` and
reconnect. Expert mode is development-API-only.

## Authentication is unavailable

Read-only inspection does not require OAuth. Production editing does.

OAuth bootstrap currently runs from an existing source checkout:

```bash
uv sync --locked --extra dev
install -m 600 .env.example .env
export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
uv run python oauth_auth.py --dev
```

Use a separate OAuth application for production. Never paste tokens into an
issue, chat, MCP configuration, or debug log.

## Production apply is refused

This is expected when any production safety gate is missing. Check that:

- the host supports MCP elicitation;
- `OSM_REQUIRE_HOST_CONFIRMATION=true`;
- `get_edit_capabilities` reports the production API and expected OSM account;
- the live account has `write_api`;
- the proposal has not expired or already been claimed;
- the exact proposal digest is supplied;
- referenced OSM versions still match.

Do not bypass a failed gate by enabling raw write tools.

## A GPX path is rejected

- Set `OSM_TRACK_IMPORT_DIR` to an absolute directory visible to the host.
- Place the file below that directory.
- Do not use symlinks that escape the directory.
- Check the configured 10 MiB and 100,000-point defaults.
- A history export with discontinuities should be split and narrowed before use.

## A preview resource does not open

Some hosts do not render `ui://` resources. Inspect the returned
`current_geojson` and `proposed_geojson` fields instead. Lack of resource UI
support does not authorize skipping review.

## Collecting a useful issue report

Include:

- operating system and MCP host/version;
- the redacted server configuration;
- whether package or source-checkout mode is used;
- output from `get_server_info` and `get_edit_capabilities`;
- the initialization or stderr error;
- whether the failure occurs before or after `tools/list`.

Remove OAuth tokens, client secrets, private GPX paths/content, and personal
location data. Report issues at
[github.com/skywinder/osm-edit-mcp/issues](https://github.com/skywinder/osm-edit-mcp/issues).
