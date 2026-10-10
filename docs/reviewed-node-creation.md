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
coverage limits. Same-family possible duplicates and retail polygons containing
the proposed shop block apply; unrelated nearby POIs still need human review.
A completed bounded inspection means only that the returned area was inspected.
The Editing API can omit enclosing polygons with no vertex in the box. Empty
results are not proof of absence. Failed, malformed, oversized or incomplete
responses return an unknown search state and no applyable proposal.

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
