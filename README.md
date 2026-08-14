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

```bash
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
uv sync --dev  # Installs both base and development dependencies
```

### 2️⃣ Configure
```bash
cp .env.example .env
# Defaults target the development sandbox (OSM_USE_DEV_API=true), which is safe
# to experiment with. See "Switching to the Production API" below before pointing
# this at the real map.
```

### 3️⃣ Test
```bash
uv run python status_check.py
```

### 4️⃣ Connect to MCP Client

**Important**: MCP servers communicate via stdin/stdout with MCP clients. Don't run `main.py` directly!

Instead, configure the server in your MCP client:
- **Cursor IDE**: Settings → Features → MCP
- **Claude Desktop**: See [MCP Client Setup](docs/MCP_CLIENT_SETUP.md)
- **VSCode (Cline)**: Add to settings.json

To test functionality without a client:
```bash
uv run python test_comprehensive.py
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
uv run python oauth_auth.py
```

### Step 5: Verify
```bash
uv run python test_comprehensive.py
```

This suite performs **real writes** — it opens changesets and creates nodes. It is
pinned to the development API and will refuse to start if configuration resolves to
production, so it is safe to run even when your `.env` targets prod.

For the unit tests (no network, no writes):
```bash
uv run pytest
```

## 🌍 Switching to the Production API

By default `.env.example` targets the development sandbox. Pointing at the real
OpenStreetMap database is a deliberate, separate step — **every edit you make becomes
a public, permanent change to the map that other people have to review or revert.**

### Step 1: Register a production OAuth app
Log in at https://www.openstreetmap.org → **My Settings → OAuth 2 applications →
Register new application**:
- **Redirect URI**: `https://localhost:8080/callback`
- **Permissions**: at minimum `read_prefs`, `write_api`, `write_changesets`

This is a *different* application from your dev-sandbox one; credentials are not shared
between the two servers.

### Step 2: Configure
In `.env`:
```bash
OSM_USE_DEV_API=false                      # switches every tool to the live API
OSM_PROD_CLIENT_ID=your_prod_client_id
OSM_PROD_CLIENT_SECRET=your_prod_client_secret
OSM_PROD_REDIRECT_URI=https://localhost:8080/callback
```
Leave `OSM_CLIENT_ID` / `OSM_CLIENT_SECRET` unset — those legacy variables override the
dev/prod switch when present.

### Step 3: Authenticate against production
```bash
uv run python oauth_auth.py
```
This writes `.osm_token_prod.json` (dev tokens live in `.osm_token_dev.json`; the server
picks the file matching `OSM_USE_DEV_API`, so the two never mix).

### Step 4: Confirm the target
```bash
uv run python status_check.py
```
On startup the server logs a `PRODUCTION MODE` warning naming the live API. If you do not
see it, you are still on the sandbox.

**Note:** `test_comprehensive.py` always runs against the dev API regardless of these
settings, by design — verification must never write test data to the live map.

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
| `close_changeset` | Finish editing session | Publishes the edit |
| `create_osm_node` | Add new point | "Add restaurant here" |
| `update_osm_node` | Move or retag a point | "Change its opening hours" |
| `create_place_from_description` | Natural language creation | "Add coffee shop called Bean There at..." |

**Not available:** creating or updating ways and relations, and deleting anything.
Those code paths exist in `server.py` but only build a request preview without sending
it, so they are deliberately not registered as MCP tools — an agent that could call them
would fail partway through an edit. To edit ways, relations, or delete elements, use
[JOSM](https://josm.openstreetmap.de/) or [iD](https://www.openstreetmap.org/edit).

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
// With uv (Recommended)
{
  "mcpServers": {
    "osm-edit": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/osm-edit-mcp",
      "env": {
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}

// Alternative: Using wrapper script (if uv has path issues)
{
  "mcpServers": {
    "osm-edit": {
      "command": "/path/to/osm-edit-mcp/run_mcp.sh",
      "args": [],
      "env": {
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```
Add to Cursor Settings → Features → MCP
</details>

<details>
<summary><b>Cursor: ~/.cursor/mcp.json entries (Dev & Prod)</b></summary>

You can also configure dev and prod entries directly in `~/.cursor/mcp.json` using the provided wrapper script `run_mcp.sh`.

```json
{
  "mcpServers": {
    "osm-edit-dev": {
      "command": "/Users/pk/repo/_mine/osm-edit-mcp/run_mcp.sh",
      "args": [],
      "env": {
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO",
        "DEVELOPMENT_MODE": "true"
      },
      "enabled": false,
      "_comment": "OSM Edit MCP Server - Development (safe testing with api06.dev.openstreetmap.org)"
    },
    "osm-edit-prod": {
      "command": "/Users/pk/repo/_mine/osm-edit-mcp/run_mcp.sh",
      "args": [],
      "env": {
        "OSM_USE_DEV_API": "false",
        "LOG_LEVEL": "INFO",
        "DEVELOPMENT_MODE": "false"
      },
      "enabled": false,
      "_comment": "OSM Edit MCP Server - Production (uses api.openstreetmap.org). Use with extreme caution; write operations require OAuth and explicit confirmation."
    }
  }
}
```

Tip: Replace the absolute path with your local path as needed. Keep production entry disabled until you are fully configured and understand the risks.

</details>

<details>
<summary><b>Claude Desktop</b></summary>

```json
// With uv (Recommended)
{
  "mcpServers": {
    "osm-edit": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/osm-edit-mcp",
      "env": {
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}

// Alternative: Using wrapper script (if uv has path issues)
{
  "mcpServers": {
    "osm-edit": {
      "command": "/path/to/osm-edit-mcp/run_mcp.sh",
      "args": [],
      "env": {
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO"
      }
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
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/osm-edit-mcp"
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
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "./osm-edit-mcp"
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

What the server actually enforces today:

- **OAuth required for writes** — changeset, node create and node update operations
  refuse to run without a valid token.
- **Changeset management** — edits are grouped into changesets you open and close.
- **Coordinate validation** — latitude/longitude bounds are checked before any write.
- **XML escaping** — tag keys and values are escaped, so names containing quotes or
  ampersands cannot corrupt or inject into a changeset.
- **Test suite pinned to the sandbox** — `test_comprehensive.py` aborts rather than
  writing to the live map.
- **Production warning on startup** — the server logs a loud warning whenever it is
  configured against the live API.

Not implemented yet — `require_user_confirmation`, `rate_limit_per_minute`,
`max_changeset_size` and the cache settings are accepted as configuration but no code
path acts on them. Do not rely on them as guardrails.

## 📊 Project Status

- **Version**: 0.1.0 (alpha)
- **Python**: 3.10+
- **License**: MIT
- **Read/search tools**: working against the live API
- **Write tools**: `create_changeset`, `close_changeset`, `create_osm_node`,
  `update_osm_node`
- **Not implemented**: way and relation create/update, and all delete operations.
  These are not registered as MCP tools — see [Available Tools](#-available-tools).

## 🌐 Remote Deployment (Make it Accessible Anywhere)

The OSM Edit MCP Server can be deployed as a web service accessible from anywhere. This is useful for:
- Team collaboration
- Integration with web applications
- Running on cloud servers
- Access from multiple devices

### 🚀 Quick Deploy with Docker

#### 1. Prerequisites
- Docker and docker-compose installed
- A server with public IP or domain name
- SSL certificate (or use the self-signed cert for testing)

#### 2. Deploy Steps

```bash
# Clone the repository
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp

# Configure environment
cp .env.example .env
# Edit .env with your OAuth credentials and API_KEY

# Deploy with Docker
chmod +x deploy.sh
./deploy.sh
```

The deploy script will:
- Build Docker containers
- Generate SSL certificates (self-signed for development)
- Start the web server on port 8000
- Set up Nginx reverse proxy on port 443

#### 3. Access Your Server

After deployment, access your server at:
- `https://your-server-ip/` (with Nginx SSL)
- `http://your-server-ip:8000/` (direct access)
- API docs: `http://your-server-ip:8000/docs`

### 📡 API Usage

All MCP functionality is exposed via REST API endpoints. Authenticate with your API key:

```bash
# Example: Find nearby amenities
curl -X POST https://your-server-ip/api/nearby-amenities \
  -H "Authorization: Bearer your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 51.5074,
    "lon": -0.1278,
    "radius_meters": 500,
    "amenity_type": "restaurant"
  }'
```

### 🔐 Security Configuration

1. **API Key**: Set a strong `API_KEY` in your `.env` file
2. **SSL Certificate**: Replace self-signed cert with a real one for production
3. **Firewall**: Only expose necessary ports (80, 443)
4. **Rate Limiting**: Configured via `RATE_LIMIT_PER_MINUTE` in `.env`

### ☁️ Cloud Platform Deployment

<details>
<summary><b>Deploy to AWS EC2</b></summary>

```bash
# Launch EC2 instance (Ubuntu 22.04 recommended)
# Install Docker
sudo apt update
sudo apt install docker.io docker-compose

# Clone and deploy
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
sudo ./deploy.sh
```
</details>

<details>
<summary><b>Deploy to DigitalOcean</b></summary>

```bash
# Create a Droplet with Docker pre-installed
# SSH into your droplet
ssh root@your-droplet-ip

# Clone and deploy
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
./deploy.sh
```
</details>

<details>
<summary><b>Deploy to Google Cloud Run</b></summary>

```bash
# Build and push to Container Registry
gcloud builds submit --tag gcr.io/PROJECT-ID/osm-edit-mcp

# Deploy to Cloud Run
gcloud run deploy osm-edit-mcp \
  --image gcr.io/PROJECT-ID/osm-edit-mcp \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars API_KEY=your-api-key
```
</details>

### 🔧 Advanced Configuration

#### Custom Domain & SSL
```nginx
# Update nginx.conf with your domain
server_name yourdomain.com;

# Use Let's Encrypt for free SSL
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

#### Environment Variables
All configuration is done via environment variables. Key settings:
- `OSM_USE_DEV_API`: Use dev (true) or production (false) API
- `API_KEY`: Authentication key for API access
- `RATE_LIMIT_PER_MINUTE`: API rate limiting
- `LOG_LEVEL`: Logging verbosity

#### Monitoring
```bash
# View logs
docker-compose logs -f

# Check health
curl https://your-server/health

# Monitor resources
docker stats
```

### 📊 Production Checklist

- [ ] Use production OSM API (`OSM_USE_DEV_API=false`)
- [ ] Set strong `API_KEY`
- [ ] Install real SSL certificate
- [ ] Configure firewall rules
- [ ] Set up monitoring/alerts
- [ ] Enable automated backups
- [ ] Configure log rotation
- [ ] Set resource limits in docker-compose.yml

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
| "Server hangs" when running main.py | This is normal! MCP servers wait for client input. Use `uv run python test_comprehensive.py` instead |
| "401 Unauthorized" | Run `uv run python oauth_auth.py` |
| "Client auth failed" | Check OAuth credentials in `.env` |
| Import errors | Run `uv sync --dev` |
| Can't see changesets | Check dev server URL (not main OSM) |
| uv: command not found | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| How do I use the server? | Configure in MCP client or run `uv run python explain_mcp_server.py` |

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