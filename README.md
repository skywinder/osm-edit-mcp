# OSM Edit MCP Server

A comprehensive Model Context Protocol (MCP) server for editing OpenStreetMap data with advanced tagging capabilities and natural language support.

## Features

- **Complete OSM CRUD Operations**: Create, read, update, and delete nodes, ways, and relations
- **Advanced Tagging System**: Natural language tag parsing and validation
- **Changeset Management**: Automated changeset creation and management
- **OAuth 2.0 Authentication**: Secure OSM API access
- **Tag Validation**: Comprehensive tag validation against OSM standards
- **Batch Operations**: Efficient bulk editing capabilities
- **Safety Features**: Development API support and confirmation prompts

## Installation

### Prerequisites

- Python 3.8+
- [Claude Desktop](https://claude.ai/download) (for MCP client)
- OpenStreetMap account with OAuth application

### Setup

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/osm-edit-mcp.git
cd osm-edit-mcp
```

2. **Install dependencies**:
```bash
# Using pip
pip install -r requirements.txt -e .

# Using uv (recommended)
uv pip install -r requirements.txt -e .
```

3. **Configure OAuth credentials**:
   - Create an OAuth application on [OpenStreetMap](https://www.openstreetmap.org/user/account) or [OSM Dev](https://master.apis.dev.openstreetmap.org/user/account)
   - Copy `.env.example` to `.env`
   - Add your OAuth credentials:

```bash
cp .env.example .env
# Edit .env with your credentials
```

4. **Initialize OSM tag standards**:
```bash
python scripts/update_osm_tags.py
```

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# OAuth Configuration
OSM_CLIENT_ID=your_oauth_client_id
OSM_CLIENT_SECRET=your_oauth_client_secret
OSM_REDIRECT_URI=https://localhost:8080/callback

# API Configuration
OSM_API_BASE_URL=https://api06.dev.openstreetmap.org  # Development API
# OSM_API_BASE_URL=https://api.openstreetmap.org       # Production API (use with caution)

# Application Settings
LOG_LEVEL=INFO
DEBUG=false
```

### Claude Desktop Integration

Add the following to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "osm-edit-mcp": {
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"],
      "env": {
        "OSM_CLIENT_ID": "your_oauth_client_id",
        "OSM_CLIENT_SECRET": "your_oauth_client_secret",
        "OSM_API_BASE_URL": "https://api06.dev.openstreetmap.org"
      }
    }
  }
}
```

## Usage

### Basic Operations

#### Creating a Node
```python
# Through Claude Desktop
"Create a restaurant node at coordinates 37.7749, -122.4194 with name 'Joe's Diner'"
```

#### Natural Language Tagging
```python
# The server understands natural language descriptions
"Add tags for a 24-hour convenience store with ATM"
# → amenity=convenience, opening_hours=24/7, atm=yes
```

#### Validating Tags
```python
# Validate tags against OSM standards
"Validate these tags: amenity=restaurant, cuisine=pizza, name=Mario's Pizza"
```

### Advanced Features

#### Batch Operations
```python
# Process multiple elements at once
"Add tourism tags to multiple POIs in this area"
```

#### Tag Merging
```python
# Intelligently merge existing and new tags
"Merge these new tags with existing ones, resolving conflicts"
```

### Safety Features

- **Development API**: Uses `dev.openstreetmap.org` by default
- **Confirmation Prompts**: Asks before irreversible operations
- **Tag Validation**: Prevents invalid tag combinations
- **Changeset Management**: Automatic changeset creation and closure

## API Reference

### Core Tools

#### Node Operations
- `create_node(lat, lon, tags, changeset_comment)`
- `update_node(node_id, lat?, lon?, tags?, changeset_comment)`
- `delete_node(node_id, changeset_comment)`
- `get_node(node_id)`

#### Way Operations
- `create_way(nodes, tags, changeset_comment)`
- `update_way(way_id, nodes?, tags?, changeset_comment)`
- `delete_way(way_id, changeset_comment)`

#### Relation Operations
- `create_relation(members, tags, changeset_comment)`
- `update_relation(relation_id, members?, tags?, changeset_comment)`
- `delete_relation(relation_id, changeset_comment)`

#### Changeset Operations
- `create_changeset(comment, tags?)`
- `close_changeset(changeset_id)`

### Tagging Tools

#### Natural Language Processing
- `parse_natural_language_tags(description, element_type, existing_tags?, location_context?)`
- `create_feature_with_natural_language(description, latitude, longitude, changeset_comment)`

#### Tag Management
- `validate_tags(tags, element_type?)`
- `suggest_tags(description, existing_tags?, limit?)`
- `merge_tags(existing_tags, new_tags, conflict_strategy?)`
- `add_tags_to_element(element_id, element_type, new_tags, changeset_comment)`
- `modify_element_tags(element_id, element_type, tag_updates, tag_removals?, changeset_comment)`

#### Tag Documentation
- `get_tag_documentation(tag_key, include_examples?)`
- `discover_related_tags(primary_tags, element_type?)`
- `explain_tags(tags)`

### Batch Operations
- `batch_tag_operations(operations, changeset_comment, dry_run?)`

### Query Tools
- `query_elements(bbox, element_type?, tags?)`
- `get_user_details()`

## Development

### Running Tests
```bash
# Run the test suite
python test_server.py

# Test natural language processing
python demo_natural_language.py
```

### Updating Tag Standards
```bash
# Fetch latest OSM tag standards
python scripts/update_osm_tags.py
```

### Development Mode
Set `DEBUG=true` in your `.env` file for verbose logging.

## Safety Guidelines

### ⚠️ Important Safety Notes

1. **Always use development API first**: Test with `https://api06.dev.openstreetmap.org`
2. **Review changes carefully**: All operations show what will be changed
3. **Use meaningful changeset comments**: Describe what and why you're changing
4. **Respect OSM guidelines**: Follow community standards and best practices
5. **Test with dry runs**: Use `dry_run=true` for batch operations

### Rate Limiting
- Maximum 10,000 API calls per hour per IP
- Built-in rate limiting and exponential backoff
- Automatic retry on rate limit errors

### Authentication
- OAuth 2.0 with secure token storage
- Automatic token refresh
- Keyring integration for credential security

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- [OpenStreetMap Wiki](https://wiki.openstreetmap.org/)
- [OSM Community Forum](https://community.openstreetmap.org/)
- [MCP Documentation](https://modelcontextprotocol.io/)

## Changelog

### v0.1.0
- Initial release with core OSM editing capabilities
- Natural language tag processing
- OAuth 2.0 authentication
- Comprehensive tag validation
- Batch operations support
- Claude Desktop integration

## Related Projects

- [OpenStreetMap](https://www.openstreetmap.org/) - The free, editable map of the world
- [Model Context Protocol](https://modelcontextprotocol.io/) - Standard for connecting AI assistants to data sources
- [Claude Desktop](https://claude.ai/download) - AI assistant with MCP support
