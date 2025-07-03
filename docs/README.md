# OSM Edit MCP Server Documentation

## 📚 Complete Documentation Index

Welcome to the comprehensive documentation for the OSM Edit MCP Server. This server enables natural language editing of OpenStreetMap data through the Model Context Protocol.

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

### Key Components
1. **OSM API Client**: Handles communication with OpenStreetMap
2. **Tag Processing Engine**: Converts natural language to structured tags
3. **Validation System**: Checks tags against OSM standards
4. **Documentation Integration**: Provides context-aware help

## 🔧 API Tools Overview

### Basic Operations
- **CRUD Operations**: Create, read, update, delete OSM elements
- **Changeset Management**: Handle OSM changesets safely
- **Query Tools**: Search and discover existing OSM data

### Natural Language Tools
- **Parse Natural Language**: Convert descriptions to tags
- **Tag Suggestions**: Get intelligent tag recommendations
- **Tag Explanation**: Convert tags back to human language
- **Tag Validation**: Verify against OSM standards

### Advanced Features
- **Batch Operations**: Handle multiple edits efficiently
- **Conflict Resolution**: Merge conflicting tag sets
- **Documentation Access**: Get OSM wiki information
- **Related Tag Discovery**: Find complementary tags

## 📋 Common Use Cases

### Adding New Features
```
User: "Add a coffee shop with WiFi"
System: Creates node with tags: amenity=cafe, internet_access=wlan
```

### Modifying Existing Features
```
User: "This restaurant also has takeaway"
System: Adds tag: takeaway=yes to existing restaurant
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
- **OAuth 2.0 only** - no password storage
- **Token management** via secure system keyring
- **Scoped permissions** for minimal access required

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