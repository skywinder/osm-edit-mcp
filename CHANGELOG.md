# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `preview_poi_polygon_create` and `review_poi_polygon_duplicates` for four
  explicitly supplied corners, four untagged vertices and one closed POI way.
  Optional isolated-node conversion preserves all tags on the area and removes
  the inspected point atomically; its version and parentage are rechecked.
- Polygon duplicate checks measure distances between complete geometries,
  including crossing edges. Synthetic demo areas are allowed only on the
  official dev API and must be labelled as synthetic evidence.
- Exact polygon readback verifies all four vertices, ordered way refs, closure,
  tags, versions and changeset, plus any source deletion. Ambiguous uploads
  recover only from an exact changeset download and readback, without retrying.

- `review_node_create_duplicates` records evidence-backed, version-bound decisions
  in a new proposal revision, atomically superseding the old preview. Distinct
  objects can be resolved without bypass flags; same/uncertain matches stay blocked.
- Node previews classify context, possible duplicates and likely duplicates using
  explicit POI types, sport lists, geometry distance, names and contacts. Pools and
  resorts no longer block pitches merely because they share `leisure`.
- Duplicate review maps distinguish context, suspicions and resolved matches,
  with reasons, evidence and existing-object OSM links. Responses explicitly
  distinguish the internal MCP preview resource from an unavailable web page.

### Security

- Recheck reviewed context and candidate versions before node creation; changes
  and incomplete searches require a fresh review. Final host approval binds the
  revision and duplicate decisions; superseded or expired proposals cannot upload.

## [0.3.0] - 2026-10-10

### Added

- `preview_node_create` for reviewed POI creation in the safe profile, with
  exact point geometry, tags, diffs and bounded nearby duplicate checks.
  Failed or incomplete searches remain unknown; possible duplicates block apply.
- `preview_node_tag_edit` for bounded tag changes to an existing node, preserving
  its coordinates and unmentioned tags and checking its inspected version.
- Capability discovery, MCP registration, owner manifest and workflow guides
  for both reviewed node operations.

### Changed

- `apply_osm_edit` creates a POI in a dedicated changeset only after genuine
  MCP host confirmation of the exact SHA-256 digest, within the proposal TTL.
  Receipts retain the actual node and changeset IDs.
- `verify_osm_edit` re-fetches created nodes and checks their exact coordinates,
  complete tags, identity, version, visibility and changeset.
- Map previews render point geometry alongside existing road-edit geometry.

### Security

- Require PyJWT 2.15.1 or later and update the runtime lock to address the
  known vulnerabilities in the previously locked 2.13.0 dependency.
- Node creation requires separate structured host confirmation in every
  environment; production remains in the safe profile with raw writes disabled.
- Canonical proposal integrity checks and atomic claims prevent altered payloads,
  concurrent writes and repeated creation. Ambiguous uploads require reconciliation
  against the original changeset and node instead of blind retries.

## [0.2.2] - 2026-09-15

### Fixed

- Natural-language keyword matching now respects word boundaries and prefers
  specific overlapping phrases. Added `car park`; negations such as
  `not wheelchair accessible` no longer get overwritten by `accessible`.
- Valhalla transport failures explain how to configure the optional local
  service or skip matching. Added an explicit setup/diagnostics guide.
- Road-edit preview describes its identity-binding OAuth requirement in the
  tool schema and returns actionable authentication guidance without building
  a proposal or sending an OSM edit.

Thanks to @chrisdebian for the hands-on reports (#7–#11). Mixed-target road
evaluation and multi-trace consensus remain separate design proposals; this
release does not implement them or weaken account/API-bound edit safeguards.

### Added

- Added a client-neutral setup skill, a functional stdio connection checker,
  and a separate Hermes guide. Discovery setup needs no OAuth; editing checks
  the expected live API, account, permissions, and safe profile in one session.
- Client-neutral `discovery` tool profile: resolve a location, search nearby,
  and retrieve details bound to the public OSM source, without OAuth/edit tools.
- Typed discovery schemas, language/country/viewbox preferences, exact category
  and tag searches, preference explanations, and timezone-aware opening hours.
- Cached, bounded public-service clients with cooldowns shared across calls and
  machine-readable errors that distinguish failures from empty results.

### Changed

- Text search now requires geographical scope; legacy expert place update/delete
  tools accept the same scope. `smart_geocode` preserves provider ordering and
  exposes prominence as `importance` instead of misleading `confidence`.
- Package smoke tests verify the supported tool names, including discovery.

## [0.2.1] - 2026-09-03

### Changed

- Made the canonical PyPI command, `uvx osm-edit-mcp`, a standalone quick-start
  step in the README while keeping the ready-to-copy MCP host configuration.
- Added live PyPI, CI, Python-version, and license badges plus a regression test
  for the public package-installation contract.

## [0.2.0] - 2026-09-03

### Added

- Review-first GPX road workflow: local track analysis, continuous subsection
  selection, nearby-way suggestions, and current/proposed GeoJSON previews.
- Optional loopback-only Valhalla map matching for diagnostic matched and
  unmatched spans.
- Persistent SQLite proposals with expiry, canonical SHA-256 digests, atomic
  claims, durable receipts, and explicit ambiguous-upload reconciliation.
- Safe capability, map-context, proposal-listing, and post-write verification
  tools.
- A `review_gpx_road_edit` MCP prompt that guides explicit GPX segment and OSM
  target selection, builds a non-writing preview, and stops before apply.
- New-road endpoint planning and partial/multi-way realignment that preserve
  existing way IDs, tags, and topology-critical nodes.
- Focused coverage for OAuth identity and scope checks, proposal concurrency,
  duplicate apply, selection, map matching, topology, and upload failures.

### Changed

- The default `safe` profile exposes reviewed proposal workflows instead of raw
  direct-write tools.
- Production apply now requires MCP host elicitation bound to the exact proposal
  digest. The legacy compatibility path remains development-only and also
  requires both the exact proposal digest and a separate host elicitation.
- Preview and apply bind to the configured API target, verified OSM account and
  permissions, referenced element versions, and the affected map context.
- All approved creates and modifications are reconciled into one transactional
  `osmChange` upload.
- The legacy HTTP wrapper is read-only and loopback-bound by default; its old
  mutation endpoints remain only as disabled HTTP 410 tombstones.
- Documentation and examples now use package-first `uvx` setup and explicitly
  distinguish inspection, preview, confirmation, and apply.

### Security

- OAuth uses PKCE, random validated state, least-privilege scopes, live
  `write_api` verification, and keyring-first token storage.
- Bearer tokens are restricted to allowlisted OSM API origins unless an operator
  explicitly configures a custom target.
- Safety gates classify the normalized API target itself: contradictory
  development/production settings are rejected, and custom targets never enable
  development-only write tools.
- Restricted imagery sources are rejected and permitted imagery requires an
  explicit operator allowlist.
- GPX paths are constrained to the configured import directory with file-size,
  point-count, traversal, and symlink protections.
- Production writes fail closed when the host cannot provide digest-bound
  elicitation.

[Unreleased]: https://github.com/skywinder/osm-edit-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.3.0
[0.2.2]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.2.2
[0.2.1]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.2.1
[0.2.0]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.2.0
