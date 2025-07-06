#!/bin/bash
# Wrapper script for running OSM Edit MCP with uv
cd "$(dirname "$0")"
exec uv run python main.py