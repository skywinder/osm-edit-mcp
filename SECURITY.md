# Security policy

## Supported versions

Security fixes are provided for the current release line:

| Version | Supported |
| --- | --- |
| 0.2.x | Yes |
| < 0.2 | No |

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability. Email
right.crew7885@fastmail.com with:

- the affected version and environment;
- a description and reproducible steps;
- the expected impact;
- a proposed fix, if available.

Remove OAuth tokens, client secrets, private GPX content, personal locations,
and other sensitive values from the report.

Response targets are an initial reply within 48 hours, a status update within
7 days, and a resolution target within 30 days for a confirmed critical issue.

## Authentication and credentials

- Register separate OAuth applications for the OSM development and production
  services. Request only `read_prefs` and `write_api`.
- OAuth bootstrap uses Authorization Code with PKCE and validates a random
  `state` value. It verifies the candidate token against the selected OSM
  service before replacing a previously stored token.
- Complete tokens are stored in the operating-system keyring by default.
- Legacy JSON token files are plaintext compatibility files, not encrypted
  backups. They are ignored unless `ALLOW_PLAINTEXT_TOKEN_FILE=true`, and files
  with permissions broader than `0600` are refused.
- Expired tokens fail closed. The server does not refresh them automatically;
  run the OAuth bootstrap again for the intended environment.
- Keep `.env`, `.osm_token_*.json`, and callback URLs containing authorization
  codes out of commits, issues, chats, and shared logs.

Create a private source-checkout configuration with:

```bash
install -m 600 .env.example .env
export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
```

Dotenv loading is explicit: a working-directory `.env` is not loaded unless
`OSM_EDIT_MCP_ENV_FILE` points to it. The file must have mode `0600`.

## Write-safety boundaries

The default `safe` profile exposes proposal-based editing, not raw mutation
tools. A production apply requires all of the following:

1. A non-expired proposal for the selected API target and verified OSM account.
2. Review of the exact operations, tags, warnings, current/proposed geometry,
   and complete SHA-256 proposal digest.
3. A later call containing that exact proposal ID and digest.
4. A separate MCP-host elicitation confirming the same complete digest.
5. Fresh OSM identity, `write_api` permission, element-version, and affected-map
   checks immediately before one atomic `osmChange` upload.

Raw direct-write tools are registered only when the explicit `expert` profile
targets the known OSM development API. Custom API targets do not enable OAuth
writes or development-only raw tools.

An ambiguous network result after upload begins is recorded as
`RECONCILE_REQUIRED`; the server does not blindly retry it.

## Data and network boundaries

- GPX paths are restricted to `OSM_TRACK_IMPORT_DIR`; traversal and symlink
  escapes are rejected. Input also has configured file-size and point-count
  limits. Keep personal tracks outside the repository.
- Remote OSM, Overpass, and Nominatim requests use HTTPS with certificate
  verification. Optional Valhalla map matching is restricted to loopback and
  may use local HTTP.
- Bearer credentials are attached only to the configured, validated OSM API
  origin. Public-service clients do not receive the OAuth token.
- The server does not implement a general client-side request-rate limiter.
  Keep requests narrow and follow each upstream service's current usage policy.
- Natural-language parsing is local and advisory. It does not select an OSM
  object or authorize a write.
- Restricted imagery providers are rejected. Any other imagery source must be
  explicitly allowlisted by the operator and still reviewed for OSM-compatible
  terms.

## Operator checklist

Before enabling an editing workflow:

- [ ] Keep `.env`, token files, GPX files, SQLite proposal state, and private
      settings untracked.
- [ ] Run `uv run --locked --extra dev python scripts/security_audit.py`.
- [ ] Run the test, Bandit, and dependency-audit gates used by CI.
- [ ] Use separate least-privilege OAuth applications for development and
      production.
- [ ] Complete representative create and update acceptance on the development
      API before configuring production.
- [ ] Verify `get_edit_capabilities` reports the intended account, API target,
      `safe` profile, and digest-bound confirmation mechanism.
- [ ] Confirm the MCP host supports elicitation before any production apply.
- [ ] Redact credentials, private paths, and location data before sharing logs.

Watch the GitHub repository and release notes for security updates.
