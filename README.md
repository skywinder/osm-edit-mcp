# OSM Edit MCP Server

A comprehensive **Model Context Protocol (MCP)** server for interacting with OpenStreetMap data. This server provides AI assistants with powerful tools to read, search, and interact with OpenStreetMap data safely and efficiently.

## 🚀 Features

### Core OSM Operations
- **Read OSM Elements**: Get nodes, ways, relations, and changesets by ID
- **Search Areas**: Find elements within geographic bounding boxes
- **Changeset Management**: Create and manage changesets for OSM edits

### Convenient Search Tools
- **Find Nearby Amenities**: Search for restaurants, cafes, hospitals, etc. around a location
- **Validate Coordinates**: Check coordinate validity and get location information
- **Place Search**: Find places by name with detailed information
- **Text Search**: Search OSM elements by text query

### Safety Features
- **Development API**: Uses OSM development server by default for safe testing
- **Coordinate Validation**: Ensures all coordinates are within valid ranges
- **Error Handling**: Comprehensive error handling with informative messages
- **Rate Limiting**: Respects OSM API rate limits

## 🛠️ Complete Setup Guide

### Prerequisites
- Python 3.8+
- OpenStreetMap account for development server
- System with browser access (for OAuth setup)

### 📋 Step-by-Step Setup

#### 1. **Install Dependencies**
```bash
git clone <repository-url>
cd osm-edit-mcp
pip install -r requirements.txt
```

#### 2. **Create Development Account**
First, create an account on the OpenStreetMap development server:
- Go to: https://api06.dev.openstreetmap.org/
- Click "Sign Up" and create an account
- **Note**: This is separate from main OSM - safe for testing!

#### 3. **Configure Environment**
Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` to ensure development mode:
```bash
# ========================================
# API Configuration (KEEP AS DEV FOR TESTING)
# ========================================
OSM_USE_DEV_API=true
OSM_DEV_API_BASE=https://api06.dev.openstreetmap.org/api/0.6

# ========================================
# OAuth Credentials (will be filled automatically)
# ========================================
OSM_DEV_CLIENT_ID=
OSM_DEV_CLIENT_SECRET=
OSM_DEV_REDIRECT_URI=https://localhost:8080/callback
```

#### 4. **OAuth Setup**
Register an OAuth application on the development server:

1. **Login** to https://api06.dev.openstreetmap.org/
2. **Go to Account Settings** → OAuth 2 Applications
3. **Click "Register new application"**
4. **Fill the form**:
   - **Name**: `OSM Edit MCP Server - Dev`
   - **Redirect URI**: `https://localhost:8080/callback`
   - **Permissions**: ✅ read_prefs, ✅ write_prefs, ✅ write_api, ✅ write_changeset_comments
5. **Copy credentials** to your `.env` file:
   ```bash
   OSM_DEV_CLIENT_ID=your_client_id
   OSM_DEV_CLIENT_SECRET=your_client_secret
   ```

#### 5. **Authenticate with Your Account**
Run the authentication script:
```bash
python oauth_auth.py
```
This will:
- Open your browser to the OAuth login page
- Ask you to login with your dev account
- Save the access token securely
- ✅ You're now authenticated!

#### 6. **Test Everything Works**
Run comprehensive tests:
```bash
python test_comprehensive.py
```

Expected results:
- ✅ **Read operations**: Working without auth
- ✅ **Write operations**: Working with auth (creates test changeset)
- ✅ **OAuth flow**: Token saved and working

#### 7. **Start the MCP Server**
```bash
python main.py
```

You should see:
```
OSM Edit MCP Server v0.1.0
API Mode: Development
API Base URL: https://api06.dev.openstreetmap.org/api/0.6
Log Level: INFO
Starting OSM Edit MCP Server...
```

### 🧪 Testing Your Setup

#### **Quick Test**
```bash
python quick_test.py
```

#### **Comprehensive Test**
```bash
python test_comprehensive.py
```

#### **Verify Your Changes on OSM Dev**
After running tests, check your changesets:
1. Go to: https://api06.dev.openstreetmap.org/user/[your-username]/history
2. Look for test changesets created by "osm-edit-mcp/0.1.0"
3. ✅ If you see them, everything is working!

### 🔧 Production Setup (Advanced)

**⚠️ ONLY for production deployments - requires extreme caution**

1. **Create production OAuth app** at https://www.openstreetmap.org/oauth2/applications
2. **Update .env**:
   ```bash
   OSM_USE_DEV_API=false
   OSM_PROD_CLIENT_ID=your_prod_client_id
   OSM_PROD_CLIENT_SECRET=your_prod_client_secret
   ```
3. **Re-authenticate** for production: `python oauth_auth.py`

### 🚨 Troubleshooting

#### **"401 Unauthorized" errors**
- Run `python oauth_auth.py` to re-authenticate
- Check your OAuth credentials in `.env`
- Verify you're using the correct API (dev vs prod)

#### **"Client authentication failed"**
- OAuth app not registered correctly
- Wrong client ID/secret in `.env`
- Try re-registering the OAuth application

#### **Can't see changesets on OSM**
- Check the correct URL: `https://api06.dev.openstreetmap.org/user/[username]/history`
- Remove URL filters like `?before=` that might hide recent changesets
- Look for changesets with `created_by=osm-edit-mcp/0.1.0`

#### **Import errors**
- Install missing dependencies: `pip install -r requirements.txt`

### ✅ Quick Status Check

Verify your complete setup:
```bash
python status_check.py
```

This will check your configuration, OAuth credentials, and authentication status.

## 🔧 Configuration

### Environment Variables (.env)

The server supports comprehensive configuration through environment variables. Copy `.env.example` to `.env` and customize:

```bash
# ========================================
# API Configuration (Dev/Prod Switching)
# ========================================
# Set to true to use development API (safe for testing)
OSM_USE_DEV_API=true

# Production API (⚠️ requires extreme caution)
OSM_API_BASE=https://api.openstreetmap.org/api/0.6

# Development API (safe for testing)
OSM_DEV_API_BASE=https://api06.dev.openstreetmap.org/api/0.6

# ========================================
# OAuth 2.0 Credentials - Production
# ========================================
OSM_PROD_CLIENT_ID=your_prod_client_id
OSM_PROD_CLIENT_SECRET=your_prod_client_secret
OSM_PROD_REDIRECT_URI=https://localhost:8080/callback

# ========================================
# OAuth 2.0 Credentials - Development
# ========================================
OSM_DEV_CLIENT_ID=your_dev_client_id
OSM_DEV_CLIENT_SECRET=your_dev_client_secret
OSM_DEV_REDIRECT_URI=https://localhost:8080/callback

# ========================================
# Logging Configuration
# ========================================
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
DEBUG=false                       # Enable debug mode
DEVELOPMENT_MODE=false            # Enable development features

# ========================================
# Safety and Rate Limiting
# ========================================
REQUIRE_USER_CONFIRMATION=true    # Require confirmation for destructive ops
RATE_LIMIT_PER_MINUTE=60         # API calls per minute
MAX_CHANGESET_SIZE=50            # Maximum operations per changeset

# ========================================
# Cache Configuration
# ========================================
ENABLE_CACHE=true                # Enable response caching
CACHE_TTL_SECONDS=300           # Cache expiration time

# ========================================
# Security Settings
# ========================================
USE_KEYRING=true                 # Use system keyring for credentials
```

### Dev/Prod API Switching

**🔄 Easy switching between development and production APIs:**

```bash
# For safe testing (recommended)
OSM_USE_DEV_API=true

# For production use (⚠️ requires extreme caution)
OSM_USE_DEV_API=false
```

The server automatically:
- Uses appropriate API endpoints
- Shows current mode in logs
- Validates configuration on startup
- Warns when using production API

### OAuth Setup
For development, follow step 4 in the setup guide above. For production:
1. Visit [OpenStreetMap OAuth Applications](https://www.openstreetmap.org/oauth2/applications)
2. Create a new application with these settings:
   - **Name**: Your application name
   - **Redirect URI**: `https://localhost:8080/callback`
   - **Scopes**: `read_prefs`, `write_prefs`, `write_api`, `write_changeset_comments`
3. Copy the Client ID and Client Secret to your `.env` file as `OSM_PROD_CLIENT_ID` and `OSM_PROD_CLIENT_SECRET`

### Log Level Configuration

Configure logging detail level:

```bash
# Show all messages (development)
LOG_LEVEL=DEBUG

# Show important messages only (production)
LOG_LEVEL=INFO

# Show only warnings and errors
LOG_LEVEL=WARNING

# Show only errors
LOG_LEVEL=ERROR
```

## 📚 Available Tools

### 1. Core OSM Data Access

#### `get_osm_node(node_id: int)`
Retrieve a specific OSM node by ID.

**Example**:
```python
# Get the Eiffel Tower node
result = await get_osm_node(1413967589)
```

#### `get_osm_way(way_id: int)`
Retrieve a specific OSM way by ID.

#### `get_osm_relation(relation_id: int)`
Retrieve a specific OSM relation by ID.

#### `get_osm_elements_in_area(min_lat, min_lon, max_lat, max_lon)`
Find all elements within a geographic bounding box.

**Example**:
```python
# Get elements in central Paris
result = await get_osm_elements_in_area(48.85, 2.29, 48.87, 2.31)
```

### 2. Search and Discovery Tools

#### `find_nearby_amenities(lat, lon, radius_meters=1000, amenity_type="restaurant")`
Find nearby amenities around a location.

**Example**:
```python
# Find restaurants within 500m of the Louvre
result = await find_nearby_amenities(48.8606, 2.3376, 500, "restaurant")
```

**Common amenity types**:
- `restaurant`, `cafe`, `bar`, `pub`
- `hospital`, `clinic`, `pharmacy`
- `school`, `university`, `library`
- `bank`, `atm`, `post_office`
- `fuel`, `parking`, `charging_station`

#### `get_place_info(place_name: str)`
Search for places by name and get detailed information.

**Example**:
```python
# Find information about "Central Park, New York"
result = await get_place_info("Central Park, New York")
```

#### `search_osm_elements(query: str, element_type="all")`
Search OSM elements using text queries.

**Example**:
```python
# Search for coffee shops
result = await search_osm_elements("coffee shop", "node")
```

### 3. Utility Tools

#### `validate_coordinates(lat: float, lon: float)`
Validate coordinates and get location information.

**Example**:
```python
# Validate coordinates for Times Square
result = await validate_coordinates(40.7580, -73.9855)
```

#### `get_server_info()`
Get server configuration and available operations.

### 4. Changeset Management

#### `create_changeset(tags: dict)`
Create a new changeset for OSM edits.

#### `get_changeset(changeset_id: int)`
Get information about a specific changeset.

#### `close_changeset(changeset_id: int)`
Close an open changeset.

## 🎯 Usage Examples

### Example 1: Finding Nearby Restaurants

```python
# Find Italian restaurants near the Colosseum in Rome
result = await find_nearby_amenities(
    lat=41.8902,
    lon=12.4922,
    radius_meters=800,
    amenity_type="restaurant"
)

# Filter for Italian restaurants
italian_restaurants = [
    r for r in result["data"]["amenities"]
    if "italian" in r["tags"].get("cuisine", "").lower()
]
```

### Example 2: Exploring a City

```python
# Search for tourist attractions in Paris
places = await get_place_info("Paris, France")
paris_coords = places["data"]["places"][0]["coordinates"]

# Find nearby tourist attractions
attractions = await find_nearby_amenities(
    lat=paris_coords["lat"],
    lon=paris_coords["lon"],
    radius_meters=2000,
    amenity_type="tourist_attraction"
)
```

### Example 3: Coordinate Validation with Location Info

```python
# Validate and get info about coordinates
result = await validate_coordinates(51.5074, -0.1278)
print(f"Location: {result['data']['location_info']['display_name']}")
print(f"Valid: {result['data']['is_valid']}")
```

## 🖥️ Claude Desktop Integration

### Configuration
Add this to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "osm-edit-mcp": {
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"],
      "env": {
        "OSM_API_BASE_URL": "https://api06.dev.openstreetmap.org/api/0.6",
        "OSM_CLIENT_ID": "your_client_id",
        "OSM_CLIENT_SECRET": "your_client_secret",
        "OSM_REDIRECT_URI": "https://localhost:8080/callback"
      }
    }
  }
}
```

### Using with Claude Desktop

Once configured, you can ask Claude to:

- **"Find me restaurants near the Eiffel Tower"**
- **"What's the coordinates of Central Park?"**
- **"Search for hospitals in downtown Seattle"**
- **"Validate these coordinates: 40.7589, -73.9851"**
- **"Get information about OSM node 123456"**

### Example Conversations

**User**: "Find me coffee shops near Times Square"

**Claude**: I'll search for coffee shops near Times Square for you.

```python
# First, let me get the coordinates of Times Square
times_square = await get_place_info("Times Square, New York")
coords = times_square["data"]["places"][0]["coordinates"]

# Now find nearby coffee shops
coffee_shops = await find_nearby_amenities(
    lat=coords["lat"],
    lon=coords["lon"],
    radius_meters=500,
    amenity_type="cafe"
)
```

**User**: "What's at coordinates 48.8584, 2.2945?"

**Claude**: Let me validate those coordinates and see what's there.

```python
location_info = await validate_coordinates(48.8584, 2.2945)
print(f"Location: {location_info['data']['location_info']['display_name']}")
# This is the Eiffel Tower in Paris!
```

## 🔒 Safety and Best Practices

### Development vs Production
- **Always use the development API** (`api06.dev.openstreetmap.org`) for testing
- **Never test write operations** on the production OSM database
- **Validate all coordinates** before sending to OSM

### Rate Limiting
- OSM API allows **10,000 requests per hour per IP**
- The server implements automatic rate limiting
- **Use caching** for frequently accessed data

### Error Handling
All tools return structured responses:
```python
{
    "success": True/False,
    "data": {...},          # On success
    "error": "...",         # On failure
    "message": "..."        # Human-readable message
}
```

## 🧪 Testing

### Comprehensive Test Suite

The server includes a comprehensive test suite that validates all 31 MCP tools:

```bash
# Run full test suite (tests all 31 tools)
python test_comprehensive.py
```

This will:
- Test all read operations (safe)
- Test write operations in simulation mode
- Test natural language processing
- Generate detailed reports (`test_report.json`)
- Create test logs (`test_results.log`)

### Manual Testing Checklist

Follow the systematic testing checklist:

```bash
# Use the comprehensive testing checklist
open TESTING_CHECKLIST.md
```

The checklist includes:
- ✅ Pre-test configuration verification
- ✅ Automated testing with the test suite
- ✅ Manual testing of all tool categories
- ✅ Configuration testing (dev/prod switching)
- ✅ Error handling validation
- ✅ Performance and security testing

### Quick Tests

```bash
# Test configuration
python -c "from src.osm_edit_mcp.server import config; print(f'Dev Mode: {config.is_development}'); print(f'API: {config.current_api_base_url}')"

# Test server info
python -c "from src.osm_edit_mcp.server import get_server_info; import asyncio; print(asyncio.run(get_server_info()))"

# Test coordinate validation
python -c "from src.osm_edit_mcp.server import validate_coordinates; import asyncio; print(asyncio.run(validate_coordinates(51.5074, -0.1278)))"

# Test place search
python -c "from src.osm_edit_mcp.server import get_place_info; import asyncio; print(asyncio.run(get_place_info('Statue of Liberty')))"
```

### Test Results

The test suite generates:
- **Console output**: Real-time test results with pass/fail status
- **test_report.json**: Detailed JSON report with metrics
- **test_results.log**: Comprehensive logs for debugging

Example test output:
```
================================================================================
OSM EDIT MCP SERVER - COMPREHENSIVE TEST REPORT
================================================================================
Test Suite Started: 2024-01-15 14:30:00
Configuration: Development
API Base URL: https://api06.dev.openstreetmap.org/api/0.6
Total Duration: 45.23 seconds
Total Tests: 31
Passed: 28
Failed: 3
Success Rate: 90.3%
```

### Expected Test Results

- **Read Operations (Tests 1-15)**: Should mostly pass
- **Write Operations (Tests 16-27)**: Expected to fail without OAuth (normal)
- **Natural Language (Tests 28-31)**: Should pass (input validation)

### Debugging Failed Tests

If tests fail unexpectedly:

1. **Check configuration**: Verify `.env` file is correctly set up
2. **Check network**: Ensure internet connectivity to OSM API
3. **Check logs**: Review `test_results.log` for detailed error messages
4. **Test individually**: Use quick test commands to isolate issues

## 🛣️ Common Use Cases

### 1. **Location Discovery**
- Find points of interest around a location
- Search for specific types of businesses
- Validate and get information about coordinates

### 2. **Urban Planning Research**
- Analyze amenity distribution in cities
- Find gaps in services (hospitals, schools, etc.)
- Study transportation infrastructure

### 3. **Travel Planning**
- Find restaurants, hotels, attractions
- Explore neighborhoods and their amenities
- Plan routes with POI information

### 4. **Data Analysis**
- Extract OSM data for analysis
- Validate geographic datasets
- Research geographic patterns

## 🔍 Advanced Queries

### Complex Overpass Queries
The server uses Overpass API for complex searches:

```python
# Find all bicycle parking within 1km of a university
result = await search_osm_elements("bicycle parking", "node")
```

### Custom Amenity Searches
```python
# Find all healthcare facilities
healthcare = await find_nearby_amenities(
    lat=40.7580, lon=-73.9855,
    radius_meters=2000,
    amenity_type="hospital"
)
```

## 📖 Additional Resources

- [OpenStreetMap API Documentation](https://wiki.openstreetmap.org/wiki/API)
- [Overpass API Documentation](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OSM Tagging Guidelines](https://wiki.openstreetmap.org/wiki/Map_Features)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test your changes with the development API
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## ⚠️ Important Notes

- **Always use development API** for testing
- **Respect OSM community guidelines**
- **Validate all data** before writing to OSM
- **Handle rate limits gracefully**
- **Never commit OAuth credentials**

---

**Ready to explore OpenStreetMap data with AI? Start with the examples above and discover the world's geographic data! 🌍**
