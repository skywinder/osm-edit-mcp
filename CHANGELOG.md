# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive CI/CD pipeline with GitHub Actions
- Unit tests for configuration and XML parsing
- Contributing guidelines and code of conduct
- Security scanning with Bandit and Safety
- Type hints throughout the codebase
- Improved error handling and logging
- Rate limiting configuration
- Cache configuration options

### Changed
- Enhanced OAuth token security with keyring integration
- Improved documentation with badges and better structure
- Updated dependencies to latest stable versions
- Better separation of dev/prod configurations

### Security
- OAuth tokens now stored securely with keyring
- Added .gitignore entries for all sensitive files
- Implemented security best practices for API calls

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