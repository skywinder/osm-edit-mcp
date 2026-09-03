# OSM Edit MCP documentation

OSM Edit MCP is a review-first local MCP server. It can inspect OpenStreetMap,
analyze a local GPX, and prepare an exact road-edit proposal. It does not grant
an agent autonomous production write authority.

## Start here

- [Quick start](quick-start-guide.md) — package-first `uvx` setup.
- [MCP client setup](MCP_CLIENT_SETUP.md) — JSON, Codex, GPX, and source modes.
- [Safe usage examples](mcp-usage-examples.md) — inspection through verification.
- [Running the server](RUNNING_SERVER.md) — stdio lifecycle and MCP Inspector.
- [Troubleshooting](MCP_TROUBLESHOOTING.md) — connection and safety-gate failures.

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

## Review model

```text
local GPX → continuous selection → current/proposed preview
          → exact digest confirmation → atomic changeset → verification
```

The implementation separates configuration/authentication, public OSM reads,
GPX selection and topology planning, persistent proposal state, optional local
Valhalla diagnostics, and atomic apply/reconciliation.

## Safety reminders

- Test editing workflows against the OSM development API.
- Keep private GPX histories outside the repository.
- Use only surveyed, locally known, or otherwise permitted evidence.
- Review every target ID, version, tag, operation, warning, and connection.
- Follow OSM community policies for imports, automated edits, and organized
  mapping when they apply.

Repository: [skywinder/osm-edit-mcp](https://github.com/skywinder/osm-edit-mcp)

License: MIT
Updated: 2026-09-03
