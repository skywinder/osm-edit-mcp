#!/bin/bash
set -eu

# Production-only launcher. Keep the API target fixed here so a stale .env or
# inherited shell variable cannot silently redirect this MCP registration.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export OSM_USE_DEV_API=false
export DEVELOPMENT_MODE=false
export OSM_API_BASE=https://api.openstreetmap.org/api/0.6
export OSM_TRACK_IMPORT_DIR="$SCRIPT_DIR/tracks"
export OSM_EDIT_MCP_ENV_FILE="$SCRIPT_DIR/.env"

exec uv run --locked osm-edit-mcp
