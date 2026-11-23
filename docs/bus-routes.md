# Map one direction of a bus route

Use the `full` MCP profile. The stop lookup, road matching and public route preview work without OAuth. An uploadable preview uses the configured OSM account and API target. Development and production have different maps and object IDs. [Connection and editing setup](MCP_CLIENT_SETUP.md)

### Run the published MCP server

For a read-only first look at the real map, add this entry to an MCP client that supports stdio, then reconnect. The same connection can later use the authenticated publication workflow described in the editing setup.

```json
{
  "mcpServers": {
    "osm-bus": {
      "command": "uvx",
      "args": ["--from", "osm-edit-mcp==0.7.0", "osm-edit-mcp"],
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
4. If the stop list is unknown, pass the complete `data.matched_geojson` object from the road match to `suggest_bus_route_stops` as `matched_geojson`. Each connected line keeps its own part number and direction. Gaps between lines are excluded from the stop search and covered distance. You can also supply the original directed trace or GPX selection. Review stops in travel order and compare the opposite-side and ambiguous lists. Pass confirmed exclusions in `excluded_node_ids`. A platform near the line is a candidate until service is confirmed.
5. Call `preview_bus_route` with the selected ways and stop nodes in travel order. Supply the source of both the path and the stops. Record excluded stops in `omitted_stops` with a label and reason. If a mapper knows the location, add `location` with latitude and longitude. The create and update previews display these coordinates as omission markers even when the OSM object is unknown. Supply `node_id` only when independently identified. Omission markers stay out of the relation members. For left-hand traffic pass `driving_side="left"`. Inspect the returned GeoJSON in iD by dropping the file onto the map. A blocked geometry preview returns the selected roads and stops in `candidate_geojson`.
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

### Choose a road at an ambiguous point

1. Call `suggest_bus_route_ways` with `include_snap_geojson=true`. Check `ambiguous_point_indices` and inspect `snap_reviews`. Indices start at zero in the original input. The response shows up to 20 points and six nearby segments per point. Each point's `candidate_count` gives the total found. To inspect additional points, pass their indices in `review_point_indices`.
2. Save `data.snap_review_geojson` as a `.geojson` file and drop it onto the iD map. Click the nearby road segments to read their OSM way IDs, distances from the survey point and mapped travel directions. “Forward” follows the OSM way's node order. The selected segment is the one used for this calculation. Ask the mapper which road the bus actually took.
3. Copy the confirmed candidate's entire `choice` object into `snap_choices`. Repeat the road match with the same ordered points or GPX selection, input kind and map provider. The matcher checks the way version and segment identity against the map. If the way changed, get a fresh review. A choice at a shared junction locates the observation on that junction. To specify the street taken after turning, include an observed point along that street.
4. Check the recalculated `ordered_way_ids`, `gaps` and `ambiguous_point_indices`. Pass `matched_geojson` to the stop search when the path is ready for stop review.

### Review the return trip

1. Select an independently observed return GPX trace or waypoints and run `suggest_bus_route_ways` in return travel order. Save the result's `data` object as `return_match`. Waypoints produce inferred paths between observations.
2. Call `review_bus_return_trip` with the confirmed outward stop node IDs in `outward_stop_ids` and the complete `return_match`. Include the outward road match as `outward_match` for a comparison of roads and junctions. Use the same OSM API target for both. Set `driving_side` to the local boarding side. Known return-direction exclusions go in `excluded_return_node_ids`.
3. Read `return_visits` in return travel order. Each entry links to a mapped stop, carries its local name and identifies its boarding side or exclusion. In `outward_stops`, follow the zero-based `return_visit_index` references to see plausible counterparts. `pair_radius_m` controls the search around an outward stop, while `corridor_radius_m` controls the search near the return path. Different names can match. Several nearby candidates or repeated visits call for field review. `missing` means the supplied searches found no nearby return visit. A return-only branch can have candidates of its own in `unpaired_return_candidate_indices`.
4. Inspect `road_comparison` for OSM ways present in just one direction, junctions without a corresponding reversed turn, and distances between paired ends of the matched geometry. Partial or gapped traces can end before the actual terminus. The report preserves road-match gaps and ambiguous observations. After checking the return roads and served stops, use `preview_bus_route` to review that direction.

### Road splits and route variants

A route relation can include a whole existing OSM way. If a surveyed turn requires part of an open way, inspect the existing interior node at the junction. Use `preview_bus_way_split` on a simple road with no parent relations. Review the split as a separate edit, apply it and pass the verified positive way IDs into a new route preview. A way with parent relations or segment-specific tags needs a relation-aware editor. A split point between nodes needs manual topology editing. The route preview supports intermediate roundabouts with distinct entry and exit nodes.

The route tool creates one PTv2 `type=route`, `route=bus` relation. The selected node platforms and stop positions come first, followed by road ways with empty roles. Each stop object keeps its tags. The current workflow handles node stops and whole road ways. Area platforms require a separate edit. For the return trip supply its own evidence and select its boarding platforms and turns. [OSM bus mapping conventions](https://wiki.openstreetmap.org/wiki/Buses)

### Update a mapped direction

Call `preview_bus_route_update` with the existing `relation_id`, an itinerary source and the changed fields. Supply a complete `stop_ids` or `way_ids` list in travel order to replace that list. Omitted lists retain their current order. For example, to change only the operator, supply `tag_changes={"operator":"Surveyed operator name"}`. A null value removes an optional tag. Other tags, including multilingual names, are preserved.

Review `relation_before` for the complete original tags and ordered members. Each entry in `changes.members` shows the removed and inserted members and their zero-based, end-exclusive ranges. Supported entry-only and exit-only boarding roles stay with retained stops. When replacing a restricted stop, pass a `boarding_roles` array in proposed stop order. Give the new platform its observed role (such as `platform_entry_only`) and use null to keep the roles of other visits. Relations using area platforms or other unsupported member roles need review in a relation-aware editor.

Set `prepare_upload=true` after checking the result. The approved upload modifies the same relation ID at the reviewed OSM version, preserving its history and parent memberships. If another mapper changes that version, prepare a fresh preview. Verification checks the exact uploaded version, including every tag and ordered member.

### Group the reviewed directions

After confirming which variants belong to the same line, pass their existing
PTv2 bus relation IDs to `preview_bus_route_master` in the desired member order.
The preview lists the direction names, terminals, versions and any route
masters they already belong to. An existing master is linked for inspection.
When all selected directions are ungrouped and share the same ref, review the
new master and its empty-role relation members. Shared network and operator
tags are carried over when all selected directions agree. The directions keep
their individual tags, stops and roads. Use `prepare_upload=true`, then
`apply_osm_edit` and `verify_osm_edit` for a reviewed creation.
[OSM route master conventions](https://wiki.openstreetmap.org/wiki/Relation:route_master)
