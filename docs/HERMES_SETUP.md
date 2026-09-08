# Hermes setup

This guide contains Hermes-specific commands. The server itself uses standard
MCP stdio and works with other clients; use the
[general setup guide](MCP_CLIENT_SETUP.md) for profiles, OAuth, and verification.

## Connect place discovery

Install `uv`, prepare the source checkout with `uv sync --locked`, and confirm
that both are accessible from the Hermes runtime. Discovery is currently
unreleased; the plain PyPI command does not yet provide this profile.

In a local terminal, register the source server:

```bash
hermes mcp add osm-places --command uv --connect-timeout 120 \
  --env OSM_TOOL_PROFILE=discovery \
  --args run --locked --project /absolute/path/to/checkout osm-edit-mcp
```

Keep `--args` last: subsequent flags are passed to the server command. The CLI
connects, lists tools, and asks which to enable; complete its selection prompt.
All three discovery tools should be available. Use an absolute executable path
if the Hermes runtime cannot find `uv`.

```bash
hermes mcp test osm-places
```

This opens a temporary connection, discovers tools, and closes it. It does not
call the discovery tools, verify OAuth, or modify an already-running agent's
MCP session. Reconnect the active host using its supported MCP reload workflow,
then call resolve → nearby search → details there. Alternatively, use the
general guide's diagnostic helper with the same server record for a separate
functional check. Do not mistake that new process for the active host.

## Editing, when requested

Follow the general guide to create distinct development/production apps,
private dotenv files, and verified identities. Register a separate development
entry using the source command:

```bash
hermes mcp add osm-edit-dev --command uv --connect-timeout 120 \
  --env OSM_EDIT_MCP_ENV_FILE=/absolute/path/to/private-dev.env \
  --args run --locked --project /absolute/path/to/checkout osm-edit-mcp
```

Keep API/profile selection in that private file, not duplicated in Hermes's
`env`. MCP subprocess environment values must be strings; generic YAML scalar
editing can produce booleans. Prefer the `--env KEY=VALUE` interface and inspect
stored value types without printing secrets. Preserve existing entries when
repairing configuration rather than adding a duplicate server.

Run the OAuth helper in the user's own terminal or a verified visible local
terminal, with the same OS user, token backend and XDG settings as Hermes.
Never ask the user to paste a callback URL into chat or an agent-private PTY.
After reconnecting, call `get_edit_capabilities` and `check_authentication`
through the active agent and check all invariants from the general guide.

Do not assume a Hermes installation supports elicitation because tool discovery
works. Verify the installed host's capabilities before production apply. Keep
`safe` and required confirmation enabled; a failed production confirmation is
not a reason to enable direct writes.

## Optional setup skill

The [repository setup skill](../skills/osm-edit-mcp-setup/SKILL.md) is independent
of Hermes. Install its directory using the skill mechanism supported by your
Hermes version. Its reference links point to the repository, so copying the
skill does not require duplicating the documentation into Hermes-specific paths.

## CLI references

The command behavior was checked against the official
[Hermes MCP CLI implementation](https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/mcp_config.py)
and [CLI argument handling](https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/main.py)
on 2026-09-08. In particular, `cmd_mcp_test` delegates to `_probe_single_server`,
whose cleanup shuts down the temporary connection. Consult `hermes mcp add
--help` for the installed version if flags differ.
