# Read-only nearby search

Branch: `feature/nearby-search`. Baseline: `uv run --locked pytest -q` — 120 passed.

1. Build a shared public Overpass executor in vertical RED/GREEN slices: bounded retry respecting Retry-After, concurrency gate, bounded TTL cache and configurable endpoint; never mirror-hop on 429.
2. Add nearby search: category OR groups with exact-tag AND constraints, bounded inputs, node coordinates / way-relation centers, haversine straight-line distances, stable URLs, deterministic deduplication, sort then limit and explicit totals.
3. Keep legacy amenity API and radius alias (reject conflicts). Require bbox or center/radius for text search; escape literal text and match multilingual name tags. Register read-only MCP tool and facade export.
4. Migrate callers: forward web search scope, explain unavailable unbounded geocoder fallback, preserve scope errors in legacy write helpers without enabling or performing writes.
5. Document semantics and examples, run offline tests and independently verify a fresh MCP process against public data. Publish a PR only with user approval; no automatic merge.

Non-goals: changing OAuth, edit safety profiles or host configuration; performing OSM edits. Leave the pre-existing untracked `node_update_hackembassy.py` untouched and never execute it.

## Verification record

- Baseline: 120 passed. RED then GREEN observed for implementation slices and follow-up multilingual/error-propagation regression tests.
- Final suite before publication: `uv run --locked pytest -q` — 172 passed.
- `uv run --locked mypy src/osm_edit_mcp` — no issues in 19 source files.
- Targeted static security review and independent code review passed.
- Actual fresh stdio `tools/list` exposes the new read-only tool; `tools/call` succeeded.
- Real nearby query at 40.197784,44.51098, radius 1200m, categories museum/park/viewpoint: 57 unique results, 15 returned with explicit truncation. First 15 IDs/order matched a separate real Overpass reference; independently calculated distances agreed within 0.1m.
- Live transport recovered from two HTTP 504 responses before HTTP 200.
- Real bounded multilingual query `Matenadaran` resolved relation 20960090, whose primary name is Armenian.
- No OSM writes or credential modifications were performed. Existing long-lived Hermes MCP connections require `/reload-mcp` after source deployment.
