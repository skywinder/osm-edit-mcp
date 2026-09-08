# LobeHub listing maintenance

The existing listing identifier is **`pk-osm-edit-mcp`**, even though the GitHub
owner is `skywinder`. Do not publish a second `skywinder-osm-edit-mcp` listing.

## Local readiness versus marketplace state

The Score page's "Includes At Least One Skill" label refers to MCP **tools**
(`toolsCount`), not an extra `SKILL.md` file. The published safe/default profile
provides 28 tools, two resource templates, and one review prompt. The production
safe profile provides 27 tools because a development-only tool is omitted.

Resource templates belong in the manifest's `resources` array with their
standard `uriTemplate` field. They are not concrete `resources/list` entries.
The review prompt must stop before applying an edit and require separate,
digest-bound host confirmation; do not weaken it to satisfy a directory check.

LobeHub's score fields are:

| Criterion | Points | How it is satisfied |
| --- | ---: | --- |
| Installation method (required) | 15 | At least one deployment option in the listing |
| README (required) | 10 | Repository README ingested by LobeHub |
| License | 8 | MIT license ingested by LobeHub |
| Tools (required) | 15 | Real tool definitions uploaded/introspected |
| Validated (required) | 20 | LobeHub validation or authenticated owner update |
| Prompts | 8 | Real prompt definition uploaded/introspected |
| Resources | 8 | Real resource/template definitions uploaded/introspected |
| Claimed | 4 | Ownership confirmed by LobeHub |
| Easy installation | 12 | A deployment option classified as non-manual |

More tools or prompts do not add points once their respective criterion is met.
Passing our tests does not itself change `isValidated`, `isClaimed`, or the
listing's deployment classification. A badge in README is a verification input,
not proof that the marketplace has completed a claim.

## Reproducible CLI introspection

After the version in `pyproject.toml` is live on PyPI, run:

```bash
uv run --locked --extra dev python scripts/check_lobehub_manifest.py
```

Requires `uvx`, Node.js 22+, and `npx`; package download needs network access.
This starts the exact released package and runs
`@lobehub/market-cli@0.0.41 plugin init` in a temporary directory. It compares
the complete tools, resources, and prompts against checked-in `lhm.plugin.json`,
including argument schemas and safety annotations. It never calls tools, logs
in, claims, publishes, updates the marketplace, or overwrites the owner manifest.

### Why a temporary metadata bridge is needed

CLI 0.0.41 looks for a description in `serverInfo.description` or `package.json`;
it does not read `pyproject.toml`. A Python MCP server can successfully answer
all capability requests and still fail `plugin init` with:

```text
Could not infer a plugin description from MCP server info or package.json.
```

The checker derives a temporary `package.json` from public `pyproject.toml`
metadata. There is no second checked-in package metadata source. LobeHub's
generated draft can infer a new identifier from the GitHub owner; the checker
discards that draft after comparing capabilities and preserves our existing ID.

## Owner update gate

### Verified least-privilege GitHub connection

On 2026-09-08, the personal public repository `skywinder/osm-edit-mcp` was
successfully claimed and updated using only `read:user` and `user:email`.
The public listing and reloaded Score page confirmed version 0.2.1,
`isClaimed=true`, `isValidated=true`, 28 tools, two resources, one prompt,
and 100/100 (A). This is marketplace metadata validation, not a production
safety certification; the server remains alpha/review-first.

CLI 0.0.41 `github connect` has no custom-scope flag and requests the provider's
broad default scopes. SDK 0.40.1 supports an explicit scope list instead:

```javascript
// sdk is a MarketSDK authenticated with the same LobeHub user session as the CLI.
const { authorize_url } = await sdk.connect.authorize('github', {
  scopes: ['read:user', 'user:email'],
});
```

Open the returned, short-lived URL locally and review GitHub's consent screen
before approving. Do not share callback URLs or tokens. Then check
`sdk.connect.getStatus('github')`: `connection.providerUsername` must match
the intended owner, and `connection.scopes` must contain only the expected
permissions (the API may return a comma-separated scope string inside an array).
No additional `github connect` process is needed: the connection belongs to the
LobeHub account, not a waiting terminal process.

```bash
npx -y @lobehub/market-cli@0.0.41 github status
npx -y @lobehub/market-cli@0.0.41 plugin claim pk-osm-edit-mcp
```

This method was not tested for organization-owned or private repositories.
Do not add `public_repo` as a presumed read-only alternative: it grants write
access to public repositories. A narrower new request does not revoke older
grants. See the [confirmed upstream report](https://github.com/lobehub/lobehub/issues/18439#issuecomment-5582959819).

Once ownership is available, review the checked-in manifest and explicitly
authorize the external update before running:

```bash
npx -y @lobehub/market-cli@0.0.41 plugin update --dir .
```

Do not use `plugin publish` to work around a failed claim. Do not accept broad
GitHub/private-repository access as a workaround. If the UI claim/rescan does not
complete, use the verified least-privilege SDK route above, or report the exact
failure with public evidence without granting additional scopes.
Avoid repeated UI submissions: the dialog asks to wait 3–5 minutes.

After update, verify version, author, capabilities, deployment options,
`isClaimed`, and `isValidated` in the
[public listing API](https://market.lobehub.com/api/v1/plugins/pk-osm-edit-mcp).

References: [score implementation](https://github.com/lobehub/lobehub/blob/main/src/features/MCP/calculateScore.ts),
[manifest schema](https://market.lobehub.com/s/publish-mcp/references/manifest),
[CLI commands](https://market.lobehub.com/s/publish-mcp/references/lhm-commands).
