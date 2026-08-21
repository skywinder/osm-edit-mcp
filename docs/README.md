# OSM Edit MCP Server Documentation

## 📚 Complete Documentation Index

The server exposes read/search helpers plus a proposal-based GPX road editor.
Natural language may describe an intent, but production object selection and
writes use stable OSM IDs, versions, visual review, and host confirmation.

## 🚀 Getting Started

### Quick Start
- **[Quick Start Guide](quick-start-guide.md)** - Get up and running in 5 minutes
- **[MCP Usage Examples](mcp-usage-examples.md)** - Practical examples of using the MCP server

### Setup & Configuration
- **[Main README](../README.md)** - Complete setup and installation guide
- **Authentication Setup** - OAuth 2.0 configuration (see main README)

## 🗣️ Natural Language Features

### Core Concepts
- **[Natural Language Processing Guide](natural-language-processing-guide.md)** - Complete guide to using natural language with OSM
- **[OSM Tagging Guide](osm-tagging-guide.md)** - Understanding OSM tags and how they work

### Validation & Standards
- **[Tag Validation and Checking Guide](tag-validation-and-checking.md)** - How to validate tags and check against OSM standards

## 📖 Reference Guides

### OSM Standards & Resources
The server integrates with official OSM resources for tag validation and documentation:

#### Primary OSM Resources
- **OSM Wiki**: https://wiki.openstreetmap.org/wiki/Map_features
- **Taginfo**: https://taginfo.openstreetmap.org/
- **OSM API Documentation**: https://wiki.openstreetmap.org/wiki/API_v0.6

#### Key Tag Categories
- **Amenities**: Restaurants, shops, services, facilities
- **Highways**: Roads, paths, transportation infrastructure
- **Buildings**: Residential, commercial, public buildings
- **Natural Features**: Parks, water bodies, terrain
- **Public Transport**: Bus stops, train stations, routes

## 🛠️ Development

### Architecture
The server is built using:
- **FastMCP Framework**: Modern MCP server implementation
- **OAuth 2.0**: Secure authentication with OpenStreetMap
- **Natural Language Processing**: Convert descriptions to OSM tags
- **Tag Validation**: Ensure data quality and standards compliance

The Python package is split by responsibility: `config.py`, `token_store.py`,
`auth.py`, `http_client.py`, and `xml_models.py` provide the core services;
`track_tools.py` plans atomic GPX road edits; `proposal_store.py` provides the
idempotent SQLite state machine; `valhalla.py` isolates optional local map
matching; `edit_tools.py` exposes safe inspection/audit tools; and `server.py`
starts the composed stdio server. Legacy raw write functions are not registered
in the safe profile.

### Key Components
1. **OSM API Client**: Handles communication with OpenStreetMap
2. **Tag Processing Engine**: Converts natural language to structured tags
3. **Validation System**: Checks tags against OSM standards
4. **Documentation Integration**: Provides context-aware help

## 🔧 API Tools Overview

### Basic Operations
- **Read and inspect**: Query stable OSM IDs, versions, tags, and geometry
- **GPX road proposals**: Create roads or reshape selected contiguous way chains
- **Atomic apply and audit**: Upload one `osmChange`, retain a receipt, and verify it

### Natural Language Tools
- **Parse Natural Language**: Convert descriptions to tags
- **Tag Suggestions**: Get intelligent tag recommendations
- **Tag Explanation**: Convert tags back to human language
- **Tag Validation**: Verify against OSM standards

### Advanced Features
- **Continuous GPX selection**: Crop long histories without sending the full trace
- **Local Valhalla diagnostics**: Detect likely mapped and unmatched spans
- **Visual resources**: Review current/proposed GeoJSON through `ui://` resources
- **Conflict detection**: Re-fetch versions, protected nodes, and write permissions

## 📋 Common Use Cases

### Adding a surveyed road
```
User: "Use points 1240 to 1395 of this GPX and preview a residential road"
System: Returns a non-writing map preview, exact operations, warnings, and digest
```

### Applying the reviewed proposal
```
User: "The preview is correct"
System: The MCP host separately asks approval for the exact production digest
```

### Understanding Map Data
```
User: "What is this tagged as?"
System: "This is a residential road with bike lanes and speed limit 30 km/h"
```

## 🔒 Safety & Best Practices

### Development Safety
- **Always use dev.openstreetmap.org** for testing
- **Validate all tags** before committing to live data
- **Follow OSM community guidelines** for data quality

### Authentication Security
- **OAuth 2.0 with PKCE and validated state** - no password storage
- **Token management** via the secure system keyring
- **Live account and `write_api` verification** before every apply

### Data Quality
- **Tag validation** against OSM standards
- **Conflict detection** and resolution
- **Changeset documentation** with meaningful comments

## 🤝 Contributing

### Documentation
- Found an error? Please submit a pull request
- Want to add examples? Contributions welcome
- Need more detail on a topic? Open an issue

### Code Contributions
- Follow the development setup in the main README
- Add tests for new features
- Update documentation for changes

## 📞 Support & Community

### Getting Help
1. Check this documentation first
2. Review the MCP Usage Examples
3. Test with the development API
4. Open an issue on GitHub if needed

### OSM Community
- **OSM Forum**: https://community.openstreetmap.org/
- **OSM Help**: https://help.openstreetmap.org/
- **IRC**: #osm on irc.oftc.net

---

**Last Updated**: January 2025
**Repository**: https://github.com/skywinder/osm-edit-mcp
**License**: MIT
