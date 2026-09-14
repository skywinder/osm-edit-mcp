# Optional local Valhalla map matching

`match_track_selection` is diagnostic, not a prerequisite for candidate search
or road-edit preview. The Python package does **not** bundle the Valhalla service
or routing tiles. Without it, skip matching and call
`suggest_track_road_candidates(selection_id=...)` directly. Candidate search
uses the selected OSM API, not Valhalla's tiles.

## Set up the optional service

1. Install Valhalla with service and data-building tools using its
   [official platform-specific build guide](https://valhalla.github.io/valhalla/start/building/).
2. Obtain an OSM PBF extract covering the survey area. Follow the official
   [routing-tile guide](https://valhalla.github.io/valhalla/mjolnir/getting_started_guide/)
   to generate `valhalla.json` and build the tiles. A running service with no
   coverage cannot establish whether a road matches.
3. Bind the HTTP service to loopback (`127.0.0.1:8002`) in the generated service
   configuration, then start `valhalla_service valhalla.json 1`. Consult the
   installed version's configuration options for the HTTP listener.
4. Check `curl --fail http://127.0.0.1:8002/status`. A successful
   [status response](https://valhalla.github.io/valhalla/api/status/) is a health
   check, not proof that the tiles cover your survey.
5. Add these values to the MCP host's server environment and restart it:

   ```json
   {
     "OSM_VALHALLA_URL": "http://127.0.0.1:8002",
     "OSM_VALHALLA_TIMEOUT_SECONDS": "30"
   }
   ```

The server reads these environment variables directly; it does not implicitly
load a copied `.env`. If using the source OAuth workflow, opt into the private
file with `OSM_EDIT_MCP_ENV_FILE` as described in the README.

## Verify and troubleshoot

- Call `get_edit_capabilities`: `valhalla.available=false` means matching is
  unavailable, not that the rest of the GPX workflow cannot run.
- Analyze a local GPX, select one continuous segment, and call
  `match_track_selection` for that selection. Review unmatched spans and
  coverage warnings. Start with a non-sensitive test track.
- Connection/timeout/HTTP failures return `success=false`, the error type,
  `optional=true` and `next_steps`. Fix the local service or skip this step.
- Invalid costing or selection inputs are errors too; do not treat every failed
  call as evidence of a missing service.
- Only loopback endpoints are accepted to avoid sending GPX geometry to a
  third-party routing service. A container has its own loopback; this package's
  default configuration assumes Valhalla is reachable on the MCP process's
  loopback interface, not a remote container hostname.

Matching needs no OSM OAuth. Road-edit proposal preview does: it binds the
proposal to the verified account and editing API. Matching neither authorizes
an edit nor proves the geometry is correct. Do not copy routed geometry into OSM
as survey evidence.
