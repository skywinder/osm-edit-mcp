# OSM Edit MCP - Quick Reference Card

## 🚀 Installation & Setup

### Using uv (Fast!)
```bash
# 1. Clone and install
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
uv sync

# 2. Configure
cp .env.example .env

# 3. Test setup
uv run python status_check.py

# 4. Run server
uv run python main.py
```

### Using pip
```bash
# 1. Clone and install
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
pip install -r requirements.txt

# 2. Configure
cp .env.example .env

# 3. Test setup
python status_check.py

# 4. Run server
python main.py
```

## 🔐 OAuth Setup (for write operations)

1. Create account at https://api06.dev.openstreetmap.org
2. Go to Settings → OAuth 2 Applications → Register new
3. Add to `.env`:
   ```
   OSM_DEV_CLIENT_ID=your_id
   OSM_DEV_CLIENT_SECRET=your_secret
   ```
4. Run: `python oauth_auth.py`

## 🛠️ Common Commands

### With uv
| Command | Purpose |
|---------|---------|
| `uv run python main.py` | Start the MCP server |
| `uv run python status_check.py` | Check configuration |
| `uv run python oauth_auth.py` | Authenticate with OSM |
| `uv run python test_comprehensive.py` | Run all tests |
| `uv run python quick_test.py` | Quick functionality test |

### Running in Background
```bash
# Using server manager (easiest)
./scripts/server_manager.sh start
./scripts/server_manager.sh status
./scripts/server_manager.sh logs
./scripts/server_manager.sh stop

# With nohup
nohup uv run python main.py > osm-mcp.log 2>&1 &

# With screen
screen -S osm-mcp
uv run python main.py
# Press Ctrl+A, then D to detach

# Check if running
ps aux | grep "[m]ain.py"
```

### With pip/python
| Command | Purpose |
|---------|---------|
| `python main.py` | Start the MCP server |
| `python status_check.py` | Check configuration |
| `python oauth_auth.py` | Authenticate with OSM |
| `python test_comprehensive.py` | Run all tests |
| `python quick_test.py` | Quick functionality test |

## 📍 Most Used Tools

### Search for Places
```python
find_nearby_amenities(lat, lon, radius, type)
# Example: Find cafes within 500m
find_nearby_amenities(51.5074, -0.1278, 500, "cafe")
```

### Get Place Information
```python
get_place_info("Central Park, New York")
```

### Validate Coordinates
```python
validate_coordinates(51.5074, -0.1278)
```

### Search by Text
```python
search_osm_elements("coffee shop", "node")
```

## 🔍 Amenity Types

- **Food**: restaurant, cafe, bar, pub, fast_food
- **Health**: hospital, pharmacy, clinic, doctors
- **Education**: school, university, library, college
- **Services**: bank, atm, post_office, police
- **Transport**: bus_station, fuel, parking, bicycle_parking
- **Shopping**: supermarket, convenience, marketplace
- **Tourism**: hotel, museum, tourist_attraction

## 📊 Test Results

✅ **Expected**: 19/19 tests passing
- Read operations: Work without auth
- Write operations: Require OAuth
- Natural language: Always works

## 🆘 Quick Fixes

| Problem | Solution |
|---------|----------|
| 401 Error | `python oauth_auth.py` |
| Import Error | `pip install -r requirements.txt` |
| No .env | `cp .env.example .env` |
| Tests fail | Check internet connection |

## 🌐 Important URLs

- **Dev Server**: https://api06.dev.openstreetmap.org
- **Your Edits**: https://api06.dev.openstreetmap.org/user/YOUR_USERNAME/history
- **OAuth Apps**: https://api06.dev.openstreetmap.org/oauth2/applications

## 🖥️ MCP Client Setup

### Cursor
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

### Claude Desktop
- Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### VSCode (Cline)
Add to `.vscode/settings.json`

## 📝 Example Requests (Any MCP Client)

- "Find Italian restaurants near the Colosseum"
- "What's at coordinates 40.7580, -73.9855?"
- "Search for hospitals in downtown Seattle"
- "Validate these coordinates: 51.5074, -0.1278"
- "Add a coffee shop called Bean There at 44.8, 20.5"