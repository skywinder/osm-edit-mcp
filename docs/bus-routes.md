# Map one direction of a bus route

Use the `full` MCP profile. The stop lookup, road matching and public route preview work without OAuth. An uploadable preview uses the configured OSM account and API target. Development and production have different maps and object IDs. [Connection and editing setup](MCP_CLIENT_SETUP.md)

### Run the published MCP server

For a read-only first look at the real map, add this entry to an MCP client that supports stdio, then reconnect. The same connection can later use the authenticated publication workflow described in the editing setup.

```json
{
  "mcpServers": {
    "osm-bus": {
      "command": "uvx",
      "args": ["--from", "osm-edit-mcp==0.5.0", "osm-edit-mcp"],
      "env": {
        "OSM_TOOL_PROFILE": "full",
        "OSM_WRITE_PROFILE": "safe",
        "OSM_USE_DEV_API": "false"
      }
    }
  }
}
```

Call `get_edit_capabilities` to see the target API, the available bus route tools and the current authentication state. The [Dushanbe example](../examples/dushanbe-bus-1/README.md) also opens in iD without an MCP installation.

### From a trip to a review

1. Start with evidence for this direction. A rider's GPS track, local knowledge of the streets and stops, or route data with documented permission for OSM can establish the itinerary. Keep the stop order and note any stops the bus skips. A published map's availability alone does not establish reuse rights. [OSM source guidance](https://www.openstreetmap.org/copyright)
2. Call `find_bus_route_stops` with ordered `locations` such as `[{"lat":38.62026,"lon":68.77705,"label":"Гагарина"}]`. Each result lists nearby mapped node IDs, local names, roles, coordinates and distances. Compare platforms on both sides of the road. A missing match is a question for the mapper. The route can use existing objects without changing their names.
3. Call `suggest_bus_route_ways` with a `selection_id` from the GPX workflow, or with ordered `points` containing latitude and longitude. For a surveyed list of stops and turns, set `input_kind="waypoints"`. Paths between waypoints are estimates. Add a point at a known turn when an alternative street fits the same stops. Review the way IDs, direction, gaps, ambiguous positions and partial ways. The returned `matched_geojson` draws each connected section separately, with gaps left visible. The tool sends geographic search boxes to the selected data service. Set `provider="editing_api"` to use the configured editing API directly.
4. If the stop list is unknown, call `suggest_bus_route_stops` with the directed trace or one connected line of matched road coordinates. Review stops in travel order and compare the opposite-side and ambiguous lists. Pass confirmed exclusions in `excluded_node_ids`. A platform near the line is a candidate until service is confirmed.
5. Call `preview_bus_route` with the selected ways and stop nodes in travel order. Supply the source of both the path and the stops. Record excluded stops in `omitted_stops` with a label, reason and optional OSM node ID. For left-hand traffic pass `driving_side="left"`. Inspect the returned GeoJSON in iD by dropping the file onto the map. A blocked geometry preview returns the selected roads and stops in `candidate_geojson`.
6. When the proposal is ready for publication, repeat the preview with `prepare_upload=true` and a documented `source_basis`. Review the map, tags, ordered members and omissions. Call `apply_osm_edit` with the resulting proposal ID and digest. The MCP host requests approval for that digest. `verify_osm_edit` reads back the relation and checks its ordered members and tags against the review. If an upload outcome is uncertain, use the original proposal ID to verify it before attempting a new proposal.

One illustrative preview with placeholder OSM IDs is shown below. Each actual ID must come from the selected API.

```json
{
  "ref": "1",
  "from_name": "Улица Гагарина",
  "to_name": "Южный терминал",
  "way_ids": [101, 102],
  "stop_ids": [201, 202],
  "source": "Mapper's own ride and stop observations",
  "source_basis": "survey",
  "omitted_stops": [],
  "prepare_upload": false
}
```

### Road splits and route variants

A route relation can include a whole existing OSM way. If a surveyed turn requires part of an open way, inspect the existing interior node at the junction. Use `preview_bus_way_split` on a simple road with no parent relations. Review the split as a separate edit, apply it and pass the verified positive way IDs into a new route preview. A way with parent relations or segment-specific tags needs a relation-aware editor. A split point between nodes needs manual topology editing. The route preview supports intermediate roundabouts with distinct entry and exit nodes.

The route tool creates one PTv2 `type=route`, `route=bus` relation. The selected node platforms and stop positions come first, followed by road ways with empty roles. Each stop object keeps its tags. The current workflow handles node stops and whole road ways. Area platforms, changes to existing route relations and grouping variants into a `route_master` require a separate edit. For the return trip supply its own evidence and select its boarding platforms and turns. [OSM bus mapping conventions](https://wiki.openstreetmap.org/wiki/Buses)
