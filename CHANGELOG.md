# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Safe GPX road workflow with track analysis, candidate suggestions, GeoJSON
  previews, explicit confirmation, and transactional `osmChange` uploads
- Continuous GPX subsection selection by indexes, timestamps, or coordinates,
  with local `ui://` map preview resources
- Optional privacy-preserving local Valhalla map matching and unmatched-span
  diagnostics
- Persistent SQLite proposal state, content/environment/account digests,
  atomic apply claiming, durable receipts, and ambiguous-upload reconciliation
- Safe capability, map-context, proposal-listing, and post-write verification tools
- Partial and multi-way road realignment that preserves way IDs, tags, and
  topology-critical nodes
- Atomic new-road endpoint connections that reuse nearby nodes or insert a
  shared node into one unambiguous nearby highway way
- Focused tests for OAuth identity/scope, proposal concurrency, duplicate apply,
  map matching, selection, HTTP write retirement, and upload timeouts
- Contributing guidelines and code of conduct
- Security scanning with Bandit and Safety
- Type hints throughout the codebase
- Improved error handling and logging

### Changed
- `create_osm_way` and `update_osm_way` now perform authenticated OSM writes
  with optimistic version handling, but raw writes are registered only in the
  explicit dev/expert profile
- Production writes now use `apply_osm_edit` with MCP host elicitation for the
  exact proposal digest; the legacy boolean-confirm tool is dev-only
- Preview/apply now bind to a live OSM UID, permission set, and allowlisted API
  target, and detect changed/new highways in the affected area
- Endpoint connection planning blocks ambiguous nodes/ways and incompatible
  layer/bridge/tunnel topology
- The legacy HTTP wrapper is read-only, fail-closed, loopback-bound by default,
  and no longer exposes direct mutation endpoints
- Updated dependencies to latest stable versions
- Better separation of dev/prod configurations

### Security
- OAuth now uses PKCE, random validated state, least-privilege scopes, live
  `write_api` verification, and keyring-only storage by default
- OAuth bearer tokens can only be sent to allowlisted OSM API origins unless an
  operator deliberately enables a custom target
- Restricted imagery providers are rejected; permitted imagery requires an
  explicit operator allowlist
- Added .gitignore entries for all sensitive files

## [0.1.0] - 2024-01-01

### Added
- Initial release with 31 MCP tools
- Core OSM operations (read/write nodes, ways, relations)
- Changeset management
- OAuth 2.0 authentication support
- Natural language processing features
- Bulk operations support
- Development/Production API switching
- Comprehensive test suite
- Claude Desktop integration
- Detailed documentation and examples

### Features
- **Core Operations**: Get, create, update, delete OSM elements
- **Search Tools**: Find nearby amenities, search by text, smart geocoding
- **Changeset Management**: Create, close, and query changesets
- **Natural Language**: Parse requests, create places from descriptions
- **Utility Tools**: Validate coordinates, export data, get statistics
- **Safety**: Development API by default, rate limiting, user confirmation

[Unreleased]: https://github.com/skywinder/osm-edit-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/skywinder/osm-edit-mcp/releases/tag/v0.1.0
