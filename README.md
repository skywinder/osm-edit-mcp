# OSM Edit MCP Server

[![CI](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/skywinder/osm-edit-mcp/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/osm-edit-mcp.svg)](https://badge.fury.io/py/osm-edit-mcp)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A powerful **Model Context Protocol (MCP)** server that enables AI assistants to interact with OpenStreetMap data. Read, search, validate, and edit map data safely with built-in protections.

## 🌟 What Can You Do?

- 🔍 **Search Places**: Find restaurants, cafes, hospitals, schools, and more
- 📍 **Validate Locations**: Check coordinates and get detailed location info
- 🗺️ **Explore Areas**: Discover what's in any geographic region
- ✏️ **Edit Safely**: Make map edits on the development server first
- 🤖 **Natural Language**: Use plain English to describe what you want

## 📦 Prerequisites

- Python 3.10+
- (Optional) [uv](https://github.com/astral-sh/uv) for fast dependency management
  ```bash
  # Install uv (optional but recommended)
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## 🚀 Quick Start (5 Minutes)

### 1️⃣ Install

#### Option A: Using uv (Recommended - Fast!)
```bash
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
uv sync --dev  # Installs both base and development dependencies
```

#### Option B: Using pip
```bash
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
pip install -r requirements.txt
```

### 2️⃣ Configure
```bash
cp .env.example .env
# No need to edit - defaults are ready to use!
```

### 3️⃣ Test
```bash
# With uv
uv run python status_check.py

# With pip
python status_check.py
```

### 4️⃣ Connect to MCP Client

**Important**: MCP servers communicate via stdin/stdout with MCP clients. Don't run `main.py` directly!

Instead, configure the server in your MCP client:
- **Cursor IDE**: Settings → Features → MCP
- **Claude Desktop**: See [MCP Client Setup](docs/MCP_CLIENT_SETUP.md)
- **VSCode (Cline)**: Add to settings.json

To test functionality without a client:
```bash
# With uv
uv run python test_comprehensive.py

# With pip
python test_comprehensive.py
```

## 🔐 Enable Write Operations (Optional)

To create or edit map data, you need OAuth authentication:

### Step 1: Create Dev Account
Visit https://api06.dev.openstreetmap.org and sign up (separate from main OSM).

### Step 2: Create OAuth App
1. Go to your [dev account settings](https://api06.dev.openstreetmap.org/user/account) → OAuth 2 Applications
2. Register new application:
   - **Name**: `OSM Edit MCP Dev`
   - **Redirect URI**: `https://localhost:8080/callback`
   - **Permissions**: Select all checkboxes

### Step 3: Add Credentials
Edit `.env` and add your OAuth credentials:
```bash
OSM_DEV_CLIENT_ID=your_client_id_here
OSM_DEV_CLIENT_SECRET=your_client_secret_here
```

### Step 4: Authenticate
```bash
# With uv
uv run python oauth_auth.py

# With pip
python oauth_auth.py
```

### Step 5: Verify
```bash
# With uv
uv run python test_comprehensive.py

# With pip
python test_comprehensive.py
```

Expected: ✅ 19/19 tests passing

## 📖 Available Tools

### 🔍 Search & Discovery

| Tool | Description | Example |
|------|-------------|---------|
| `find_nearby_amenities` | Find places around a location | "Find restaurants within 500m" |
| `get_place_info` | Search places by name | "Where is Central Park?" |
| `search_osm_elements` | Text search for any element | "Search for coffee shops" |
| `smart_geocode` | Convert address to coordinates | "10 Downing Street, London" |

### 📍 Location Tools

| Tool | Description | Example |
|------|-------------|---------|
| `validate_coordinates` | Check if coordinates are valid | `51.5074, -0.1278` |
| `get_osm_elements_in_area` | Get all elements in a box | "What's in this area?" |
| `get_osm_statistics` | Area statistics | "How many restaurants?" |

### 🗺️ OSM Data Access

| Tool | Description | Example |
|------|-------------|---------|
| `get_osm_node` | Get node by ID | Node details |
| `get_osm_way` | Get way by ID | Street/building info |
| `get_osm_relation` | Get relation by ID | Complex features |

### ✏️ Editing Tools (Requires Auth)

| Tool | Description | Example |
|------|-------------|---------|
| `create_changeset` | Start editing session | Required for edits |
| `create_osm_node` | Add new point | "Add restaurant here" |
| `create_place_from_description` | Natural language creation | "Add coffee shop called Bean There at..." |

## 💡 Usage Examples

### Find Nearby Restaurants
```python
# Find Italian restaurants near the Colosseum
result = await find_nearby_amenities(
    lat=41.8902, lon=12.4922,
    radius_meters=500,
    amenity_type="restaurant"
)
```

### Validate Coordinates
```python
# Check if coordinates are valid and get location info
result = await validate_coordinates(51.5074, -0.1278)
# Returns: "London, England, United Kingdom"
```

### Natural Language Search
```python
# Parse natural language requests
result = await parse_natural_language_osm_request(
    "Find coffee shops near the Eiffel Tower"
)
```

## 🖥️ MCP Client Integration

### Quick Setup for Popular Clients

<details>
<summary><b>Cursor IDE</b></summary>

```json
// With uv
{
  "mcpServers": {
    "osm-edit": {
      "command": "uv",
      "args": ["run", "python", "/path/to/osm-edit-mcp/main.py"],
      "cwd": "/path/to/osm-edit-mcp"
    }
  }
}

// With pip/python
{
  "mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "/path/to/osm-edit-mcp"
      }
    }
  }
}
```
Add to Cursor Settings → Features → MCP
</details>

<details>
<summary><b>Claude Desktop</b></summary>

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"]
    }
  }
}
```
Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
</details>

<details>
<summary><b>Continue.dev</b></summary>

```json
{
  "mcpServers": [
    {
      "name": "osm-edit",
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"]
    }
  ]
}
```
Add to `~/.continue/config.json`
</details>

<details>
<summary><b>Cline (VSCode)</b></summary>

```json
{
  "cline.mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["./osm-edit-mcp/main.py"]
    }
  }
}
```
Add to VSCode settings or `.vscode/settings.json`
</details>

📖 **[Full MCP Client Setup Guide](docs/MCP_CLIENT_SETUP.md)** - Detailed instructions for all clients

### Example Queries
- "Find restaurants near Times Square"
- "What's at coordinates 48.8584, 2.2945?"
- "Search for hospitals in Seattle"

## 🛡️ Safety Features

- ✅ **Development API by default** - Safe testing environment
- ✅ **OAuth protection** - Edits require authentication  
- ✅ **Rate limiting** - Respects API limits
- ✅ **Input validation** - Prevents invalid data
- ✅ **Changeset management** - Groups edits properly

## 📊 Project Status

- **Version**: 0.1.0
- **Tests**: 100% passing (19/19)
- **Python**: 3.10+
- **License**: MIT

## 🧪 Testing

```bash
# Quick test
python quick_test.py

# Full test suite
python test_comprehensive.py

# Check your edits
# Visit: https://api06.dev.openstreetmap.org/user/YOUR_USERNAME/history
```

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Server hangs" when running main.py | This is normal! MCP servers wait for client input. Use `python test_comprehensive.py` instead |
| "401 Unauthorized" | Run `python oauth_auth.py` |
| "Client auth failed" | Check OAuth credentials in `.env` |
| Import errors | Run `pip install -r requirements.txt` or `uv sync --dev` |
| Can't see changesets | Check dev server URL (not main OSM) |
| uv: command not found | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| How do I use the server? | Configure in MCP client or run `python explain_mcp_server.py` |

## 📚 Documentation

- [Quick Reference Card](QUICK_REFERENCE.md) - All commands on one page
- [MCP Client Setup](docs/MCP_CLIENT_SETUP.md) - Cursor, Claude, VSCode, etc.
- [Running the Server](docs/RUNNING_SERVER.md) - Background, monitoring, auto-restart
- [Quick Start Guide](docs/quick-start-guide.md)
- [API Examples](docs/mcp-usage-examples.md)
- [OSM Tagging Guide](docs/osm-tagging-guide.md)
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 🔗 Links

- [GitHub Repository](https://github.com/skywinder/osm-edit-mcp)
- [Issue Tracker](https://github.com/skywinder/osm-edit-mcp/issues)
- [OpenStreetMap](https://www.openstreetmap.org)
- [Model Context Protocol](https://modelcontextprotocol.io)

---

**Ready to explore the world's map data? Start with the Quick Start above! 🌍**