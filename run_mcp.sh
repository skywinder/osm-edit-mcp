#!/bin/bash
# Wrapper script for running OSM Edit MCP with uv
cd "$(dirname "$0")"
if [ -f .env ]; then
    export OSM_EDIT_MCP_ENV_FILE="$PWD/.env"
fi
exec uv run --locked osm-edit-mcp
