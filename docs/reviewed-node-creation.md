# Reviewed POI node creation

`preview_node_create` is available in the full tool profile with the default
`safe` write profile, on development and production. It sends no OSM mutations.
It requires verified OAuth with `write_api`, binding the proposal to the
intended account and API.

```python
preview_node_create(
    latitude=27.332994,
    longitude=33.693731,
    tags={"shop": "supermarket"},
    changeset_comment="Add supermarket observed on site",
    changeset_source="survey",
)
```

Use this example only when the coordinates and classification are independently
confirmed on site. Never copy names, hours or proprietary map coordinates from
Google Maps. Omit unconfirmed attributes.

Coordinates must be finite and in range, with at most seven decimal places.
The preview exposes the exact seven-decimal values sent to OSM, without silent
rounding. Supply 1–20 string tags including an explicit POI classification.
Tags and changeset metadata follow the existing node-edit limit: nonempty
strings, at most 255 UTF-8 bytes, without control characters. Restricted map
providers are rejected as evidence.

Duplicate inspection reads an approximately 100 m bounding area from the
selected Editing API, including tagged nodes, ways and relations. It returns
exact candidate IDs, versions, tags, geometry, API provenance, bounds and
coverage limits. Each candidate has `classification` (`context_only`,
`possible_duplicate`, `likely_duplicate`), `reasons`, `blocking`, `distance_m`
and an `osm_url` on the selected OSM environment. A shared key such as `leisure`
does not imply a duplicate: a pitch, swimming pool and beach resort are different
explicit types. Containment of a pitch by a resort is context alone. A retail
area containing a proposed shop still requires review.
A completed bounded inspection means only that the returned area was inspected.
The Editing API can omit enclosing polygons with no vertex in the box. Empty
results are not proof of absence. Failed, malformed, oversized or incomplete
responses return an unknown search state and no applyable proposal.

Duplicate thresholds are review heuristics in metres, selected by the proposed
object type, and returned in `duplicate_search.policy` (version 1):

| Proposed type | Possible duplicate within | Likely duplicate within |
| --- | ---: | ---: |
| `leisure=pitch` | 35 m | 8 m; 15 m with a matching sport |
| `leisure=swimming_pool` | 20 m | 5 m |
| `leisure=beach_resort` | 75 m | 15 m |
| Other POI types | 25 m | 5 m |

Distance alone is not a duplicate signal across different explicit types.
Matching types within the possible threshold require review; the likely
threshold increases the classification. Matching names (including name variants)
or contacts flag candidates throughout the returned search area, even across
type differences; with a matching type they indicate a likely duplicate.
Shared operator contacts can be false matches and still require inspection.
An unspecified existing type near a matching classification key is possible.
Different names never cancel a duplicate signal. Sports are compared as sets,
including `;` lists. A missing/unspecified sport or `multi` leaves uncertainty;
different sports reduce likelihood but never establish distinctness by themselves.
Two nearby pitches with different sports can therefore still require review.

Distances use the proposed point and the nearest point on existing line/area
geometry, not a centre. Points inside a returned area have distance zero.
Nearby line distances use a local metric projection; node distances use a
spherical great-circle calculation. Relation geometry remains a conservative
union of returned member geometries, so holes or fragmented boundaries can
produce extra candidates for review. Search limits remain visible even when
all candidates are resolved. This feature creates points only; it does not add
polygon creation or change neighbouring geometry.

Resolve a blocked preview with a separate, non-writing tool:

```python
review_node_create_duplicates(
    proposal_id="<preview proposal ID>",
    proposal_digest="<complete preview SHA-256>",
    decisions=[{
        "osm_type": "way",
        "osm_id": 123,  # use an actual ID returned in this proposal
        "expected_version": 3,  # the inspected candidate version
        "decision": "distinct_object",
        "reason": "Separate volleyball court in front of the pools; tennis court is east",
        "evidence_source": "user report from on-site observation",
    }],
)
```

Every blocking candidate needs an explicit decision in each review. Optional
decisions about context candidates are allowed, but unknown IDs/types, duplicate
decisions and wrong versions are rejected. `reason` and `evidence_source` are
required nonempty text with the same 255 UTF-8 byte/control-character limit as
changeset metadata. State the real evidence; do not invent a survey.
`distinct_object` resolves that candidate while retaining its classification,
reasons and version. `same_object` keeps creation blocked and directs the caller
to edit the existing object. `uncertain` stays blocked. There is no force/skip
flag. Reviewing duplicates neither changes OSM nor supplies upload approval.

Review first repeats the complete bounded search and checks the previous
snapshot. On success it atomically stores a new proposal ID, digest and TTL,
marking the parent `SUPERSEDED`. Concurrent reviews or upload claims cannot
reuse the parent. `revision` identifies the parent ID/digest and revision number.
The new digest binds exact coordinates/tags, all candidates and context,
candidate versions, decisions, reasons and evidence. Review the new proposal
before requesting separate approval; approval of an older digest is invalid.

The map resource shows the proposed point in red, context in grey, unresolved
suspicions in orange and matches reviewed as distinct in green. Its object list
includes OSM links, classifications, reasons and evidence sources. `preview_uri`
is an internal MCP HTML resource (`ui://`), not a normal web URL. This server
does not currently configure or host a web preview page: `web_preview_url` is
`null` and `web_preview_status` explicitly states that limitation.

Review the complete diff, Point geometry (`[longitude, latitude]`), tags,
changeset comment/source, candidates, warnings, API target, account, expiry and
complete SHA-256. The digest binds exact write content and map context. The
default TTL is 1800 seconds. Expired proposals require a new preview and fresh
approval.

Only a later `apply_osm_edit(proposal_id=..., proposal_digest=...)` can request
an upload. A separate, genuine MCP elicitation must accept `confirm=true` and
the same complete digest. Node creation requires this on development too,
even when generic development confirmation is disabled. Unsupported or empty
structured approval fails closed.

After approval the server freshly verifies account, permissions, map context
and element limits, atomically claims the durable proposal, creates a dedicated
changeset, and sends one `osmChange` containing one new node. A supplied shared
`changeset_id` is refused because content matching cannot safely recover its
creation result. The receipt stores real `node_id` and `changeset_id`, mapping,
URLs and readback verification. Readback must match ID, version, changeset,
visibility, exact coordinates and the complete tags.

The fresh search must still match the reviewed snapshot, including reviewed
candidate versions and supporting geometry nodes. New suspicious candidates,
changed versions, changed geometry, failed searches or incomplete results stop
the write before changeset creation. Create a fresh preview and repeat review
and user approval. Even an unrelated map change currently invalidates the
snapshot conservatively. A duplicate decision never authorizes bypassing a
search failure.

Repeated apply returns the receipt without another upload. Once upload starts,
a timeout or ambiguous response triggers changeset download and node readback.
Only one exact create-node operation with matching content resolves the result.
Otherwise durable state stays `RECONCILE_REQUIRED`; empty or unavailable
evidence never authorizes a retry. `verify_osm_edit` can later repeat read-only
recovery, even after preview TTL, and persist a verified receipt. Keep the old
proposal until recovery completes; do not rebuild it to repeat an uncertain
upload.

Unit tests use isolated state and mocked HTTP. Live acceptance must use the
official development API with separate authorization and genuine host approval.
Never create test objects in production.

On Hermes/Umbrel preserve `/opt/data`, private env/keyring paths and existing
node-tag editing. Source updates need a fresh MCP connection. Discovery in a
new process does not prove the gateway reloaded its long-lived connection.
Use the installed host's supported targeted MCP reload procedure. Do not
update Hermes, switch profiles or restart the shared gateway to bypass missing
elicitation support.
