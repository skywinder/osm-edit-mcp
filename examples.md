# OSM Edit MCP Server - Usage Examples

This document provides practical examples of how to use the OSM Edit MCP Server with various AI assistants.

## 🏗️ Quick Start with Claude Desktop

1. **Configure Claude Desktop**: Add the server configuration to Claude Desktop's config file:
   ```json
   {
     "mcpServers": {
       "osm-edit-mcp": {
         "command": "python",
         "args": ["/path/to/your/osm-edit-mcp/main.py"],
         "env": {
           "PYTHONPATH": "/path/to/your/osm-edit-mcp/src"
         }
       }
     }
   }
   ```

2. **Start Claude Desktop** and you'll have access to all OSM tools!

## 📍 Common Use Cases

### 1. Finding Nearby Places

**Ask Claude:**
> "Find restaurants within 500 meters of Times Square in New York"

**What happens:**
- Claude uses `find_nearby_amenities(40.7580, -73.9855, 500, "restaurant")`
- Returns nearby restaurants with names, cuisine types, and distances

### 2. Validating Coordinates

**Ask Claude:**
> "Are these coordinates valid: 40.7580, -73.9855? What location is this?"

**What happens:**
- Claude uses `validate_coordinates(40.7580, -73.9855)`
- Returns validation status and detailed location information

### 3. Finding Places by Name

**Ask Claude:**
> "What are the coordinates of the Sydney Opera House?"

**What happens:**
- Claude uses `get_place_info("Sydney Opera House")`
- Returns coordinates and detailed address information

### 4. Searching for Map Elements

**Ask Claude:**
> "Find all hospitals in downtown area"

**What happens:**
- Claude uses `search_osm_elements("hospital", "node")`
- Returns OSM hospital nodes with locations and details

### 5. Getting OSM Data

**Ask Claude:**
> "Get information about OSM node 123456"

**What happens:**
- Claude uses `get_osm_node(123456)`
- Returns node data including coordinates and tags

## 🔧 Advanced Examples

### Creating a Travel Guide

**Ask Claude:**
> "Create a travel guide for Central Park area - find nearby restaurants, cafes, and attractions within 1km"

**Claude will:**
1. Get Central Park coordinates using `get_place_info("Central Park, New York")`
2. Find restaurants with `find_nearby_amenities(lat, lon, 1000, "restaurant")`
3. Find cafes with `find_nearby_amenities(lat, lon, 1000, "cafe")`
4. Search for attractions with `search_osm_elements("attraction", "node")`
5. Format everything into a comprehensive guide

### Location Analysis

**Ask Claude:**
> "Analyze the amenities around these coordinates: 51.5074, -0.1278"

**Claude will:**
1. Validate coordinates with `validate_coordinates(51.5074, -0.1278)`
2. Find various amenities (restaurants, shops, transport, etc.)
3. Provide a detailed breakdown of the area

### Route Planning Support

**Ask Claude:**
> "Find all subway stations between Times Square and Central Park"

**Claude will:**
1. Get coordinates for both locations
2. Search for subway stations in the area
3. Plot them geographically

## 📊 Tool Reference

### Read Operations (Safe, No Confirmation)
- `get_osm_node(node_id)` - Get node details
- `get_osm_way(way_id)` - Get way details
- `get_osm_relation(relation_id)` - Get relation details
- `get_osm_elements_in_area(bbox)` - Get elements in bounding box
- `get_changeset(changeset_id)` - Get changeset info

### Search Operations (Safe, No Confirmation)
- `find_nearby_amenities(lat, lon, radius, type)` - Find amenities
- `validate_coordinates(lat, lon)` - Validate coordinates
- `get_place_info(place_name)` - Find place by name
- `search_osm_elements(query, element_type)` - Search elements

### Write Operations (⚠️ Require Confirmation)
- `create_changeset(comment, tags)` - Create changeset
- `create_osm_node(lat, lon, tags, changeset_id)` - Create node
- `close_changeset(changeset_id)` - Close changeset

### Utility Operations
- `get_server_info()` - Get server status

## 🎯 Natural Language Examples

The beauty of using this MCP server with Claude is that you can ask questions in natural language:

**Geographic Questions:**
- "What's at coordinates 40.7580, -73.9855?"
- "Find the nearest coffee shop to the Eiffel Tower"
- "Are there any hospitals within 2km of downtown Sydney?"

**Data Exploration:**
- "Show me all the parks in this area: -73.97,-73.95,40.77,40.79"
- "What OSM data is available for way ID 12345?"
- "List all restaurants with outdoor seating in this neighborhood"

**Planning Questions:**
- "I'm visiting London - find attractions near Westminster"
- "Plan a food tour route with restaurants within 500m of each other"
- "Find all public transport stations between these two points"

## 🛡️ Safety Features

- **Development API**: Uses `api06.dev.openstreetmap.org` by default for safe testing
- **Confirmation Required**: Write operations require explicit user confirmation
- **Rate Limiting**: Respects OSM API rate limits (10,000 calls/hour)
- **Error Handling**: Graceful handling of API errors and network issues

## 📚 Next Steps

1. **Start Simple**: Begin with coordinate validation and place searches
2. **Explore**: Try different amenity types and search queries
3. **Advanced**: Combine multiple tools for complex analysis
4. **Contribute**: Add new tools or improve existing ones

## 🔗 Useful Resources

- [OpenStreetMap API Documentation](https://wiki.openstreetmap.org/wiki/API)
- [OSM Tag Documentation](https://wiki.openstreetmap.org/wiki/Tags)
- [Overpass API Documentation](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [Nominatim API Documentation](https://nominatim.org/release-docs/develop/api/Overview/)

---

*Happy mapping! 🗺️*