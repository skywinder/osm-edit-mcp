# Quick start

OSM Edit MCP is a local stdio server. Your MCP host starts and stops it; there
is no port to open and no background daemon to manage.

## 1. Install uv

Install [uv](https://docs.astral.sh/uv/) and confirm that `uvx` is on the PATH
visible to your MCP host:

```bash
uvx --version
```

## 2. Add the server

Use this configuration in a JSON-based MCP host:

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

Restart the host after saving the configuration. The first launch downloads the
released package into an isolated uv environment.

## 3. Verify read-only operation

Ask the host to call `get_server_info`. Then call
`get_edit_capabilities` and check:

- `environment` is `development`;
- `write_profile` is `safe`;
- raw write tools are not registered;
- production confirmation is digest-bound MCP elicitation.

Authentication may be reported as unavailable during this read-only quick
start. That is expected.

## 4. Try a safe inspection

Use a small bounding box:

```text
inspect_map_context(
  bbox="-0.1280,51.5068,-0.1268,51.5078",
  highway_only=true,
  max_elements=500
)
```

This reads current OSM data; it does not create a proposal or write a changeset.

## 5. Add a local GPX directory

To use the review workflow, add an absolute directory to the server environment:

```json
{
  "OSM_TRACK_IMPORT_DIR": "/absolute/path/to/local-gpx"
}
```

Keep personal tracks outside the repository. Start with
`analyze_gpx_track`, select only the relevant continuous section, and review its
local selection preview. Building an edit proposal with
`preview_track_road_edit` is still non-writing, but requires OAuth so the
proposal can be bound to a verified OSM identity and API target.

See [MCP client setup](MCP_CLIENT_SETUP.md) for other client formats and
[safe usage examples](mcp-usage-examples.md) for the complete review sequence.
