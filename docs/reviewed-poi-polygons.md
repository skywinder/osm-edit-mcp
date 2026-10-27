# Reviewed four-sided POI polygons

`preview_poi_polygon_create` creates an area: four new untagged corner nodes and
one closed OSM way. The POI tags belong to the way. A repeated first **node ID**
closes the way; a fifth node at the same coordinates does not count as closure.
`preview_node_create` remains appropriate for a POI whose physical boundary is
unknown. It never infers a polygon from one coordinate.

For a sports pitch with a visible outline, OSM guidance recommends drawing the
playing area with `leisure=pitch`, `sport=*` and the verified `surface=*`:
<https://wiki.openstreetmap.org/wiki/Tag:leisure%3Dpitch>.
A sand volleyball court is not necessarily a regulation-size beach volleyball
court. Its real corners, size and orientation must come from independent,
permitted evidence, not an assumed standard or proprietary map.

```python
preview_poi_polygon_create(
    corners=[
        {"latitude": 27.2431670, "longitude": 33.8442196},
        {"latitude": 27.2431670, "longitude": 33.8443004},
        {"latitude": 27.2433110, "longitude": 33.8443004},
        {"latitude": 27.2433110, "longitude": 33.8442196},
    ],
    tags={"leisure": "pitch", "sport": "volleyball", "surface": "sand"},
    changeset_comment="Demonstrate a four-sided volleyball area on dev",
    changeset_source="synthetic demonstration geometry; not surveyed",
    demonstration=True,
)
```

These example corners are a **synthetic dev-only demonstration**, roughly
16 by 8 metres, centred on the previously supplied coordinate and aligned
north/south. They do not establish this court's real boundary. `demonstration`
is false by default; true is rejected outside the official dev API and its
source must explicitly identify synthetic/demonstration geometry.

Supply exactly four distinct corners in boundary order, clockwise or
counterclockwise. The tool preserves their exact seven-decimal coordinates
without rounding and adds closure. It rejects self-intersections, touching
opposite edges, zero-length sides, collinear adjacent sides, degenerate areas,
polar/dateline-spanning polygons and diameters over 500m. `area=no` is refused.
The usual 1–20 explicit POI tags and 255 UTF-8 byte metadata limits apply.
This bounded tool does not create multipolygons, reuse neighbouring vertices,
change existing ways or infer a rectangle from a centre.

## Converting an isolated point into an area

Inspect the existing node and supply `replace_node_id` with
`expected_node_version` in the preview. The tool reads its exact coordinates,
version and complete tags, and queries `/node/{id}/ways` and
`/node/{id}/relations`. Failed or incomplete parentage checks block the preview.
Any parent way or relation requires manual topology review instead.

The source must lie within the proposed area. **Every source tag must be
preserved on the new way**; conversion cannot silently discard an existing
name, contact, access or other tag. The preview explicitly includes removal
of this one source node. The dedicated changeset atomically creates the four
vertices and way and deletes the old isolated node. The deletion is strict:
if another object references the node before upload, the whole upload fails
instead of silently leaving two POIs. OSM retains the old node's history;
this is no history purge.

The source is shown as a replacement candidate, not dismissed as a separate
object. Every other suspicious candidate still requires duplicate review.

## Review, confirmation and verification

Search covers the entire polygon plus at least 100m around it. Its radius is
computed from all corners and exposed alongside the exact bounds and context
snapshot. Duplicate policy version 2 measures the minimum distance between
complete geometries; overlapping areas and crossing edges have distance zero,
including crossings with no contained corner. Different leisure types remain
context; different sports never cancel a nearby same-type suspicion.
Enclosing areas omitted by the Editing API and conservative relation-member
geometry remain explicit coverage limits.

`review_poi_polygon_duplicates(proposal_id, proposal_digest, decisions)` uses
the same evidence-backed, version-bound decisions as node creation. All
blocking candidates need a decision. `same_object` or `uncertain` stay blocked;
`distinct_object` requires a reason and real evidence source. A replacement
source cannot be declared distinct to avoid conversion safeguards. Reviewing
creates a new ID/digest/TTL and marks the parent `SUPERSEDED` atomically.
No review tool uploads or approves a write.

Review the complete Polygon GeoJSON, four corner coordinates, ordered way
refs, tags, warnings, any source deletion and the final digest. The map shows
areas and source-point replacement; synthetic geometry is prominently labelled.
`preview_uri` is an internal MCP HTML resource, not an HTTP link; no web
proposal page is currently hosted (`web_preview_url=null`).

Use ordinary `apply_osm_edit` with that exact final digest. Genuine separate
host confirmation is required on **development too**, even if generic dev
confirmation is disabled. Shared changesets are rejected. Before upload the
server rechecks account, complete context, source version/tags/coordinates,
source parentage and the 5-operation (6 with conversion) API limits.

Success requires exact mapping and readback of the way and all four vertices:
ordered references, closure by first ID, complete tags only on the way,
coordinates, visibility, version 1 and correct changeset. Conversion also
verifies the source's next history version is deleted in this same changeset.
An ambiguous upload or failed readback becomes `RECONCILE_REQUIRED`.
Recovery needs an exact changeset download plus readback of all elements and
any deletion; empty or incomplete evidence never permits another upload.
`verify_osm_edit` repeats read-only verification/recovery, and repeated apply
returns the stored receipt without another upload.
