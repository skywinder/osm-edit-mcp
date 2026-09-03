# OSM Edit MCP - Quick Reference Card

## 🚀 Installation & Setup

### Released package

Configure the MCP client to launch the package directly:

```bash
uvx osm-edit-mcp
```

### Local development checkout

```bash
# 1. Clone and install
git clone https://github.com/skywinder/osm-edit-mcp
cd osm-edit-mcp
uv sync --locked --extra dev

# 2. Configure
install -m 600 .env.example .env
export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"

# 3. Test setup
uv run python status_check.py

# 4. Configure in MCP client (see docs/MCP_CLIENT_SETUP.md)
# To test: uv run python test_comprehensive.py
```

## 🔐 OAuth Setup (for write operations)

1. Create account at https://api06.dev.openstreetmap.org
2. Go to Settings → OAuth 2 Applications → Register new
3. Add to `.env`:
   ```
   OSM_DEV_CLIENT_ID=your_id
   OSM_DEV_CLIENT_SECRET=your_secret
   ```
4. Export `OSM_EDIT_MCP_ENV_FILE="$PWD/.env"` and run
   `uv run python oauth_auth.py --dev` from the development checkout.

## 🛠️ Common Commands

| Command | Purpose |
|---------|---------|
| Configure in MCP client | Server runs via client (see setup below) |
| `uvx osm-edit-mcp` | Run the released MCP package over stdio |
| `uv run python status_check.py` | Check configuration |
| `uv run python oauth_auth.py` | Authenticate with OSM |
| `uv run python test_comprehensive.py` | Run the dev-API integration suite |

### Understanding MCP Servers
```bash
# ⚠️ MCP servers communicate via stdin/stdout
# They are started by MCP clients, not run directly!

# To test server functionality:
uv run python test_comprehensive.py

# To use the server:
# 1. Configure in your MCP client (Cursor, Claude Desktop, etc.)
# 2. The client will start/stop the server automatically
```

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

### Add or Realign a Road from GPX
```python
# GPX paths are relative to OSM_TRACK_IMPORT_DIR (default: ./tracks)
analyze_gpx_track(gpx_path="survey-road.gpx")
create_track_selection(
    track_id="<track_id>",
    segment_id="trk-0-seg-0",
    start_point_index=1240,
    end_point_index=1395,
)
suggest_track_road_candidates(
    selection_id="<selection_id>"
)
preview_track_road_edit(
    action="create",
    selection_id="<selection_id>",
    tags={"highway": "track", "surface": "gravel"},
    changeset_comment="Add surveyed track",
    changeset_source="survey",
)
# Review GeoJSON, warnings, element counts, and the complete digest before calling:
apply_osm_edit(proposal_id="...", proposal_digest="...")
```

For existing roads use `action="update"`, omit `tags`, and provide the explicitly
selected ordered `target_way_ids`. One segment is handled per preview. Applying
also requires the MCP host to confirm the same exact proposal digest.

Crop a long history export to the one surveyed path first. On macOS, use JOSM to
compare the GPX with OSM, gpx.studio to crop/split, GPXSee for quick GPX/KML
viewing, or Google Earth Pro for KMZ. Save the selected result under `tracks/`;
that directory's contents are intentionally ignored by Git.

## 🔍 Amenity Types

- **Food**: restaurant, cafe, bar, pub, fast_food
- **Health**: hospital, pharmacy, clinic, doctors
- **Education**: school, university, library, college
- **Services**: bank, atm, post_office, police
- **Transport**: bus_station, fuel, parking, bicycle_parking
- **Shopping**: supermarket, convenience, marketplace
- **Tourism**: hotel, museum, tourist_attraction

## 📊 Test Results

- `uv run pytest` — unit tests, no network, no writes
- `uv run python test_comprehensive.py` — integration suite; performs real writes and is
  pinned to the dev API, so it aborts if configuration resolves to production

Coverage by category:
- Read operations: work without auth
- Write operations: require OAuth; changesets, nodes, and ways are supported
- GPX road edits: preview plus explicit confirmed transactional apply
- Relation edits and deletes: not implemented, not exposed as tools
- Natural-language parsing and search work without auth; the safe profile does
  not expose natural-language write shortcuts

## 🆘 Quick Fixes

| Problem | Solution |
|---------|----------|
| 401 Error | `uv run python oauth_auth.py` |
| Import Error | `uv sync --locked --extra dev` |
| No dotenv configuration | `install -m 600 .env.example .env && export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"` |
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
      "command": "uvx",
      "args": ["osm-edit-mcp"]
    }
  }
}
```

### Claude Desktop
- Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### VS Code (Cline)

Open Cline → MCP Servers → Configure MCP Servers and add the top-level
`mcpServers` object from `examples/cline_settings.json`. This is Cline's MCP
settings file, not `.vscode/settings.json`.

## 📝 Example Requests (Any MCP Client)

- "Find Italian restaurants near the Colosseum"
- "What's at coordinates 40.7580, -73.9855?"
- "Search for hospitals in downtown Seattle"
- "Validate these coordinates: 51.5074, -0.1278"
- "Analyze this local GPX and show a selected-segment preview"
