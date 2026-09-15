# OSM Edit MCP

[![MCP Badge](https://lobehub.com/badge/mcp/pk-osm-edit-mcp)](https://lobehub.com/mcp/pk-osm-edit-mcp)
[![PyPI](https://img.shields.io/pypi/v/osm-edit-mcp.svg)](https://pypi.org/project/osm-edit-mcp/)
[![CI](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/osm-edit-mcp.svg)](https://pypi.org/project/osm-edit-mcp/)
[![License](https://img.shields.io/pypi/l/osm-edit-mcp.svg)](LICENSE)

Find places in OpenStreetMap and review road edits from your local GPX surveys
through an MCP-compatible assistant.

**Alpha, review-first:** nothing is edited automatically. Road changes need an
authenticated OSM account, an exact preview and separate confirmation.

## Fastest start

You need **Python 3.10+**, [uv](https://docs.astral.sh/uv/), and an MCP client
that supports local stdio servers. No repository clone, Docker, API key or
Valhalla installation is needed for place search.

Add this server to your client's MCP configuration (merge it with any existing
servers), then reconnect:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "uvx",
      "args": ["osm-edit-mcp"],
      "env": {
        "OSM_TOOL_PROFILE": "discovery"
      }
    }
  }
}
```

The client downloads the [released package](https://pypi.org/project/osm-edit-mcp/)
on first launch and starts it for you. This profile exposes **only three
read-only place-search tools** and needs no OAuth. Searches use public OSM
services and send the search area/query to them.

Try asking your assistant:

> Find museums and parks within 1 km of Matenadaran in Yerevan. Show OSM links.

Clients with a configuration form: command **`uvx`**, argument
**`osm-edit-mcp`**, environment **`OSM_TOOL_PROFILE=discovery`**.
If the client cannot find `uvx`, use its absolute path. See
[client setup](docs/MCP_CLIENT_SETUP.md) or [Hermes setup](docs/HERMES_SETUP.md).

You can also start the server from a terminal:

```bash
uvx osm-edit-mcp
```

It waits for an MCP client; it is **not an interactive terminal app or website**.
The bare command uses the default full profile, unlike the discovery-only
configuration above.

## GPX and editing: what else needs setup?

Keep the same command and args; replace the server's `env` above with:

```json
{
  "OSM_TOOL_PROFILE": "full",
  "OSM_USE_DEV_API": "true",
  "OSM_WRITE_PROFILE": "safe",
  "OSM_REQUIRE_HOST_CONFIRMATION": "true"
}
```

Reconnect, then call `get_edit_capabilities` to check the selected API and
authentication status. This enables GPX tools and the review-first workflow on
the **development sandbox**; it does not log you in or authorize an edit.

**To make edits:** register a development OSM OAuth app and authenticate it with
the source checkout's `oauth_auth.py --dev` helper, following the
[authentication guide](docs/MCP_CLIENT_SETUP.md#editing-authentication).
Keep credentials in a private file, not in this JSON or chat. Once the guide's
private file contains the profile/API settings, replace `env` with only
`OSM_EDIT_MCP_ENV_FILE` pointing to that file; do not leave conflicting settings
in both places. Preview the proposal, review it, and confirm its exact digest.
Real-map edits need a **separate production app/configuration**, development
acceptance first, and an MCP host that supports confirmation (elicitation).

| What you want to do | What to configure, and why |
| --- | --- |
| Inspect a GPX and preview a selected section | No OAuth. Set `OSM_TRACK_IMPORT_DIR` to your private GPX folder, or supply inline GPX XML. |
| Find candidate roads | Uses the selected editing API. The dev sandbox is **not a copy of the real map**. |
| Preview a road-edit diff | Set up OSM OAuth: the proposal is bound to your account and API target even before any write. |
| Apply an edit | Review the exact proposal and confirm its digest separately in the MCP client. Production needs a host that supports elicitation. |
| Optionally match a track to a routing graph | Run local Valhalla with regional routing tiles. Skip this if you do not need matching; nothing installs it automatically. |

A selected-track preview is **not** an OSM edit proposal. Start with the
[working GPX example](docs/README.md#try-a-local-preview-without-oauth-or-valhalla).
Before editing, follow the [OAuth and production guide](docs/MCP_CLIENT_SETUP.md#editing-authentication).
Never treat one GPS trace as ground truth.

## Detailed guides

[Full guide and examples](docs/README.md) ·
[Nearby search](docs/NEARBY_SEARCH.md) ·
[Optional Valhalla](docs/VALHALLA.md) ·
[Troubleshooting](docs/MCP_TROUBLESHOOTING.md) ·
[Changelog](CHANGELOG.md)

## Contributing and license

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE).
OSM edits must also follow community guidelines and source-licensing requirements.
