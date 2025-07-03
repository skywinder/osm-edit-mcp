# OSM Edit MCP Server

A simple Model Context Protocol (MCP) server for OpenStreetMap editing operations. This server provides basic read, fetch, and update capabilities for OSM data through the MCP protocol.

## Features

- **Read OSM Data**: Fetch nodes, ways, and relations by ID
- **Search Operations**: Find OSM elements within bounding boxes
- **Update Operations**: Create and modify OSM elements
- **Changeset Management**: Handle OSM changesets for data modifications
- **OAuth 2.0 Authentication**: Secure access to OSM API
- **Development API Support**: Safe testing with dev.openstreetmap.org

## Installation

### Prerequisites

- Python 3.8+
- [Claude Desktop](https://claude.ai/download) or another MCP client
- OpenStreetMap account for API access

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd osm-edit-mcp
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your OSM OAuth credentials
   ```

4. **Set up OAuth Application**:
   - Go to https://www.openstreetmap.org/oauth2/applications
   - Create a new application
   - Set redirect URI to `http://localhost:8080/callback`
   - Add your client ID and secret to `.env`

## Usage

### With Claude Desktop

1. **Update Claude Desktop configuration**:

   Edit your Claude Desktop configuration file (`claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "osm-edit-mcp": {
         "command": "python",
         "args": ["/path/to/your/osm-edit-mcp/main.py"],
         "env": {
           "PYTHONPATH": "/path/to/your/osm-edit-mcp"
         }
       }
     }
   }
   ```

2. **Start Claude Desktop** and the OSM Edit MCP server will be available

### Available Operations

The MCP server provides these tools:

- **`get_osm_node`**: Fetch a specific OSM node by ID
- **`get_osm_way`**: Fetch a specific OSM way by ID
- **`get_osm_relation`**: Fetch a specific OSM relation by ID
- **`search_osm_elements`**: Search for OSM elements in a bounding box
- **`create_osm_node`**: Create a new OSM node
- **`update_osm_node`**: Update an existing OSM node
- **`create_changeset`**: Create a new OSM changeset
- **`close_changeset`**: Close an OSM changeset
- **`authenticate_osm`**: Authenticate with OSM API

## Configuration

### Environment Variables

Set these in your `.env` file:

```bash
# OSM API Configuration
OSM_API_BASE_URL=https://api06.dev.openstreetmap.org/api/0.6
OSM_CLIENT_ID=your_oauth_client_id
OSM_CLIENT_SECRET=your_oauth_client_secret
OSM_REDIRECT_URI=http://localhost:8080/callback

# Server Configuration
LOG_LEVEL=INFO
```

### Development vs Production

**For Testing (Recommended)**:
- Use `OSM_API_BASE_URL=https://api06.dev.openstreetmap.org/api/0.6`
- This is the development API that won't affect real map data

**For Production**:
- Use `OSM_API_BASE_URL=https://api.openstreetmap.org/api/0.6`
- ⚠️ **CAUTION**: This modifies real OpenStreetMap data!

## Safety Guidelines

1. **Always test with dev.openstreetmap.org first**
2. **Never commit OAuth credentials to version control**
3. **Respect OSM API rate limits** (10,000 requests/hour)
4. **Use meaningful changeset comments**
5. **Follow OpenStreetMap tagging conventions**

## Development

### Project Structure

```
osm-edit-mcp/
├── main.py                 # Entry point
├── src/
│   └── osm_edit_mcp/
│       ├── __init__.py
│       └── server.py       # MCP server implementation
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
└── README.md
```

### Testing

Test the server import:
```bash
python -c "from src.osm_edit_mcp.server import mcp; print('Server imported successfully')"
```

The server uses stdio transport and should be connected via an MCP client like Claude Desktop.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test with dev.openstreetmap.org
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Resources

- [OpenStreetMap API Documentation](https://wiki.openstreetmap.org/wiki/API_v0.6)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
- [OSM OAuth 2.0 Setup](https://wiki.openstreetmap.org/wiki/OAuth)
