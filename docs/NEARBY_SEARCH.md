# Read-only nearby search

`search_nearby_places` queries **public OpenStreetMap data via Overpass**, irrespective
of the editing API's dev/prod selection. No OAuth or edits are involved.
These examples are invocations, not claimed live results.

## MCP examples

Call `search_nearby_places` with:

```json
{"lat":40.197784,"lon":44.51098,"radius_meters":1200,"categories":["museum","park","viewpoint"],"limit":15}
```

Find an exact tag combination (no regex/Overpass QL accepted):

```json
{"lat":40.197784,"lon":44.51098,"radius_meters":1500,"tag_filters":{"leisure":"hackerspace"},"limit":20}
```

Multiple categories are **OR**. `tag_filters` are exact **AND** constraints on
*every* category, or can be used alone. For instance, categories `["museum",
"gallery"]` plus `{"wheelchair":"yes"}` finds either type with that exact tag.
Omitting both categories and tag filters fails; it never silently searches restaurants.
Unknown categories return all supported names.

| Tag key | Supported category names |
| --- | --- |
| `amenity` | restaurant, cafe, bar, pub, hospital, pharmacy, bank, atm, toilets, drinking_water, school, library, parking, place_of_worship |
| `tourism` | museum, gallery, attraction, viewpoint, hotel, hostel, information, artwork |
| `leisure` | hackerspace, park, garden, playground, sports_centre, swimming_pool |
| `historic` | monument, memorial, castle, ruins, archaeological_site |
| `shop` | supermarket, convenience, bakery, books, clothes |

Limits: radius integer **1–10000 metres** (default 1000), limit integer **1–100**
(default 20), up to 20 category entries and 10 exact tag pairs. Coordinates must
be finite and in range. Keys/values must be nonempty, at most 255 characters,
with no control characters. Quotation marks/backslashes are escaped.

## Results and distances

`data.places` contains type, ID, tags, location, location_source, distance_meters,
and stable `https://www.openstreetmap.org/{type}/{id}` URLs. All nodes, ways and
relations are queried in one compact `out center tags` request (no geometry dump).

- Nodes use their coordinates; ways/relations use Overpass **bounding-box centers**,
  not entrances, geometric centroids or nearest boundary points.
- Distances are deterministic haversine **straight-line** metres (Earth radius
  6371008.8m), rounded to millimetres for stable output, **not precision claims**.
  They are not walking/driving distances and do not account for barriers.
- `distance_type` is `straight-line`; `distance_reference` is `query_location`.
- Overpass selects geometry near the point: a polygon's center may be outside the
  requested radius. Those objects are retained and their actual center-distance
  is reported; no false "every center is within radius" assertion is made.
- Missing/invalid coordinates yield null location/distance, sorted last; never
  substitute invented distances.
- Deduplicate by `(type,id)`, sort by reported distance then type/ID, **then** limit.
  `total` is the unique result count returned by the complete Overpass response,
  `count` is the number delivered, and `truncated` indicates local limiting.
  These are not claims that OSM contains every real-world place. Upstream timeout
  remarks are errors, not empty/complete successes.

## Legacy compatibility and geographical text search

`find_nearby_amenities` remains an **amenity-only** exact search, preserving
`data.amenities`, `amenity_type`, query location and radius. Its `radius` alias is
accepted; conflicting `radius` and `radius_meters` fail. Neither supplied defaults
to 1000m. Default amenity is still restaurant. Museums and parks must use the new
category search because their correct keys are `tourism` and `leisure`.

Call `search_osm_elements` with either scope:

```json
{"query":"museum","element_type":"all","lat":40.197784,"lon":44.51098,"radius_meters":1200,"limit":20}
```

```json
{"query":"Matenadaran","element_type":"all","bbox":"44.50,40.19,44.53,40.21","limit":20}
```

Bbox order: **west,south,east,north**, ordered and at most 0.25° in each dimension;
antimeridian-spanning bboxes are rejected. Do not combine bbox and point scope.
`query` is literal case-insensitive text, not user regex, searched only in
`name`, `alt_name`, `official_name` and their `:*` variants (e.g. `name:en`,
`name:ru`), plus amenity/tourism/leisure/historic/shop values. Name keys use a
fixed anchored regex, never a user-supplied key regex. Thus `Matenadaran` or
`Матенадаран` can match translated tags even with an Armenian primary name.
Global all-tag regex scans have
been removed. Missing scope returns a helpful error without an Overpass call.
The familiar `data.elements` key is retained, with the same count/truncation fields.
For bbox searches `distance_reference=bbox_center` and `query_location` explicitly
contains that reference point.

The web `/api/search` request accepts these scope, element_type and limit fields.
Address-only `smart_geocode` still uses Nominatim, but no longer performs an
unbounded Overpass fallback: `data.overpass_fallback` explains how to run a scoped
search instead.

## Transport and operational bounds

All three searches share one unauthenticated executor:

- One active request sequence per server process, including retry waits.
- At most three attempts for transport errors/timeouts and HTTP 429/502/503/504.
  Backoff is 1s then 2s; valid numeric or HTTP-date Retry-After may increase it.
- Never switches mirrors on rate limits. Retry-After above the 30s wait budget
  fails with an explicit retry-later error rather than shortening the cooldown.
- Each request has a 30s hard timeout; whole operation (including queue) has a
  160s hard budget, below a typical 180s MCP host timeout.
- Complete successful responses only: process-local 30s TTL cache, up to 32 queries,
  defensive copies. No failures or partial responses are cached.
- Operator can choose a single endpoint using `OSM_OVERPASS_URL` in the process
  environment; default `https://overpass-api.de/api/interpreter`. Only HTTP(S), no
  credentials embedded in the URL. This is not an automatic mirror list.

To use the checkout with a **fresh** stdio client, launch:

```bash
uv run --locked --directory /opt/data/tools/osm-edit-mcp osm-edit-mcp
```

An already-running server does not hot-reload source changes. This implementation
does not restart any service, change host configuration, or push/commit code.
