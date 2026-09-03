# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/skywinder/osm-edit-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.2.0
