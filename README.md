# OSM Edit MCP Server

A comprehensive Model Context Protocol (MCP) server for editing OpenStreetMap (OSM) data. This server provides AI assistants with the ability to safely create, read, update, and manage OSM data through a secure, well-designed interface.

**🔗 GitHub Repository**: https://github.com/skywinder/osm-edit-mcp

## 🎯 Features

- **Full OSM CRUD Operations**: Create, read, update, and delete OSM nodes, ways, and relations
- **Changeset Management**: Automatic changeset creation and management
- **OAuth 2.0 Authentication**: Secure authentication with OSM using OAuth 2.0
- **Safety First**: Built-in validation, user consent, and error handling
- **Development & Production APIs**: Support for both live OSM and development server
- **Rate Limiting**: Respects OSM API rate limits and best practices
- **FastMCP Implementation**: Uses the latest FastMCP framework for optimal performance

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- OSM account with OAuth 2.0 application

### Installation with uv

1. **Clone the repository**:
   ```bash
   git clone https://github.com/skywinder/osm-edit-mcp.git
   cd osm-edit-mcp
   ```

2. **Create virtual environment and install dependencies**:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your OAuth credentials
   ```

### OAuth 2.0 Setup

You need to create an OAuth 2.0 application in OpenStreetMap:

1. **Login to OSM**: Go to https://www.openstreetmap.org/login
   - Use account: `right.crew7885@fastmail.com`

2. **Create OAuth Application**:
   - Visit: https://www.openstreetmap.org/oauth2/applications
   - Click "Register new application"
   - **Name**: `OSM Edit MCP Server`
   - **Redirect URIs**: `https://localhost:8080/callback`
   - **Scopes**: Select all required scopes:
     - ✅ Read user preferences
     - ✅ Modify user preferences
     - ✅ Modify the map
     - ✅ Comment on changesets
     - ✅ Read private GPS traces
     - ✅ Upload GPS traces

3. **Configure Credentials**:
   The OAuth application has been pre-registered:
   - **Application ID**: 8523
   - **Client ID**: `Rzs-aBhMIdzXQLPfsx_33MAvmtmpjez-VAUc5sljttk`
   - **Client Secret**: `x_JbyRrIwV1espCfRwe6mRkEXcZgXn2uiUoNxA66izw`

4. **Update `.env` file**:
   ```bash
   OSM_OAUTH_CLIENT_ID=Rzs-aBhMIdzXQLPfsx_33MAvmtmpjez-VAUc5sljttk
   OSM_OAUTH_CLIENT_SECRET=x_JbyRrIwV1espCfRwe6mRkEXcZgXn2uiUoNxA66izw
   OSM_OAUTH_REDIRECT_URI=https://localhost:8080/callback
   ```

### Running the Server

```bash
# Start the MCP server
python main.py

# Or using the installed command
osm-edit-mcp
```

### Development Setup

For development with additional tools:

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Linting
flake8 src/
```

## 📖 Usage

### MCP Tools

The server provides the following MCP tools:

#### Node Operations
- `create_node`: Create a new OSM node
- `get_node`: Retrieve node information
- `update_node`: Update existing node
- `delete_node`: Delete a node

#### Way Operations
- `create_way`: Create a new OSM way
- `get_way`: Retrieve way information
- `update_way`: Update existing way
- `delete_way`: Delete a way

#### Relation Operations
- `create_relation`: Create a new OSM relation
- `get_relation`: Retrieve relation information
- `update_relation`: Update existing relation
- `delete_relation`: Delete a relation

#### Changeset Operations
- `create_changeset`: Create a new changeset
- `close_changeset`: Close an active changeset
- `get_changeset`: Get changeset details

#### Query Operations
- `query_elements`: Search for OSM elements by various criteria

### MCP Resources

The server exposes these MCP resources:

- `changeset://{id}`: Access changeset data
- `element://{type}/{id}`: Access individual OSM elements
- `user://details`: Get current user information
- `capabilities://`: Server capabilities and API limits

### Example Usage

```python
# Example tool calls through MCP
{
  "tool": "create_node",
  "arguments": {
    "lat": 51.5074,
    "lon": -0.1278,
    "tags": {
      "amenity": "cafe",
      "name": "Example Cafe"
    }
  }
}

{
  "tool": "create_way",
  "arguments": {
    "nodes": [1001, 1002, 1003],
    "tags": {
      "highway": "residential",
      "name": "Example Street"
    }
  }
}
```

## 🔒 Security Considerations

⚠️ **IMPORTANT**: This server allows editing of live OpenStreetMap data. Please:

- **Always test first** using the development API (`USE_DEV_API=true`)
- **Follow OSM guidelines** for data quality and attribution
- **Use meaningful changeset comments** describing your changes
- **Respect OSM community standards** and mapping conventions
- **Be cautious with bulk operations** - they can affect many users

### Built-in Safety Features

- **OAuth 2.0 Authentication**: Secure token-based authentication
- **Input Validation**: Comprehensive validation of all inputs
- **Rate Limiting**: Respects OSM API rate limits
- **User Consent**: Prompts for confirmation on destructive operations
- **Audit Logging**: Complete logging of all operations
- **Error Handling**: Graceful handling of API errors and edge cases

## 🛠️ Development

### Project Structure

```
osm-edit-mcp/
├── src/osm_edit_mcp/
│   ├── __init__.py       # Package initialization
│   └── server.py         # Main MCP server implementation
├── main.py               # Entry point
├── pyproject.toml        # Project configuration
├── requirements.txt      # Dependencies
├── .env.example         # Environment template
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

### Key Dependencies

- **mcp>=1.2.0**: Model Context Protocol framework
- **httpx**: Async HTTP client for OSM API
- **pydantic**: Data validation and settings management
- **authlib**: OAuth 2.0 implementation
- **structlog**: Structured logging

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes with tests
4. Run the test suite: `pytest`
5. Submit a pull request

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=osm_edit_mcp

# Run specific test
pytest tests/test_server.py::test_create_node
```

## 📋 API Reference

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `OSM_OAUTH_CLIENT_ID` | OAuth 2.0 client ID | - | Yes |
| `OSM_OAUTH_CLIENT_SECRET` | OAuth 2.0 client secret | - | Yes |
| `OSM_OAUTH_REDIRECT_URI` | OAuth redirect URI | `https://localhost:8080/callback` | Yes |
| `USE_DEV_API` | Use development API | `false` | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `RATE_LIMIT_REQUESTS` | Max requests per minute | `300` | No |

### Error Codes

| Code | Description |
|------|-------------|
| `OSM_AUTH_ERROR` | OAuth authentication failed |
| `OSM_API_ERROR` | OSM API request failed |
| `OSM_VALIDATION_ERROR` | Input validation failed |
| `OSM_RATE_LIMIT` | Rate limit exceeded |
| `OSM_PERMISSION_ERROR` | Insufficient permissions |

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Acknowledgments

- **OpenStreetMap Community**: For providing the amazing OSM platform
- **Model Context Protocol**: For the excellent MCP framework
- **Anthropic**: For developing the MCP specification

## ⚠️ Disclaimer

This is an independent project and is not officially affiliated with OpenStreetMap Foundation. Always follow OSM community guidelines and terms of service when editing map data.

---

**Repository**: https://github.com/skywinder/osm-edit-mcp
**Author**: pk (right.crew7885@fastmail.com)
**License**: MIT
