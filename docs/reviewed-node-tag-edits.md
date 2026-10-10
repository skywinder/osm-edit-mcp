# Reviewed existing-node tag edits

`preview_node_tag_edit` adds a review-first single-node tag patch to the existing
safe profile. It does not upload, create a changeset, or move/delete an element.
The raw production-write restriction and mandatory production host elicitation
are unchanged.

## Inputs

All five arguments are required:

- `node_id`: positive integer (no string, boolean or float coercion).
- `expected_version`: positive integer from a fresh inspection of the exact node.
- `tag_changes`: object containing 1–20 keys; string sets/replaces a tag, JSON
  `null` explicitly removes one. Unmentioned tags remain unchanged. Removing an
  absent key or submitting a patch with no net effect is rejected.
- `changeset_comment`: meaningful explanation of the edit.
- `changeset_source`: actual evidence, such as `user report: permanent closure`.
  Do not claim an on-site survey or observation date that was not supplied.

Keys, non-null values, and changeset metadata must be nonempty, at most 255 UTF-8
bytes, and contain no control characters. Restricted map-provider sources are
rejected. The node is fetched live, its identity/visibility/version are checked,
and its original coordinate strings are retained. Local and server changeset
limits apply at preview and again before upload.

## Operator workflow (fresh stdio process)

1. Launch the normal installed/source-checkout MCP stdio server with its existing
   private configuration. For this checkout use `uv run --no-sync osm-edit-mcp`
   from the repository directory. Do not print or replace the env file or tokens.
2. Through that fresh MCP connection, use `tools/list`, `get_edit_capabilities`,
   `check_authentication`, and `get_osm_node` to check the new tool, production
   target, verified account, permission and latest node version.
3. Call the preview with only evidenced tag changes. Example closure patch:

   ```json
   {
     "node_id": 11233641471,
     "expected_version": 3,
     "tag_changes": {"amenity": null, "disused:amenity": "restaurant"},
     "changeset_comment": "Record reported permanent closure of Nor Aleppo",
     "changeset_source": "user report: permanent closure"
   }
   ```

   Version `3` is an example based on the preceding inspection; re-fetch and use
   the actual current version. A mismatch requires fresh inspection and preview.
4. Stop and show the user the full returned current/proposed tags, unchanged
   coordinates, `operations.modify_nodes`, warning, account, target, proposal ID
   and complete SHA-256 digest. Other lifecycle/name/operating-information tags
   are preserved, not automatically declared correct; review them explicitly.
5. In a later call use normal `apply_osm_edit(proposal_id, proposal_digest)`.
   The client must support genuine structured MCP form elicitation. Display the
   actual server request and collect the human response for `confirm` and the
   full `proposal_digest`. Only relay that real response; never synthesize or
   automatically accept it. A host returning `accept` with `{}` cannot approve
   the required form. If no capable human-facing host is available, stop.
6. The existing durable store, API/account binding, expiry, atomic claim,
   version checks, one atomic upload and replay protection remain in force.
   Modified-node preflight additionally requires one existing node, complete
   snapshot coverage and unchanged ID/version/coordinates; live ID, version,
   visibility, tags and coordinates must still match the preview snapshot.
7. Upload verification requires exactly the approved node diff result (same ID,
   next version), then exact tag and coordinate readback. Missing/wrong diff or
   readback becomes `RECONCILE_REQUIRED`; do not retry. Finally call
   `verify_osm_edit` and re-fetch the node before reporting publication.

The existing durable proposal database allows a fresh stdio process to load a
proposal by ID; use the same private configuration and state location. Rebuild
an expired proposal rather than editing database state or bypassing approval.

All implementation tests use isolated proposal stores and mock HTTP transports.
They do not validate production host UX or publish OSM data.
