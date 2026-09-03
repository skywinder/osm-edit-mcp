#!/usr/bin/env python3
"""Diagnose package-first MCP startup for Cursor.

Run from a development checkout with:
    uv run --locked python debug_mcp_cursor.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SAFE_ENV = {
    "OSM_USE_DEV_API": "true",
    "OSM_WRITE_PROFILE": "safe",
    "OSM_REQUIRE_HOST_CONFIRMATION": "true",
}


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a diagnostic subprocess from the project root."""
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )


print("🔍 MCP Server Debug Tool for Cursor")
print("=" * 50)

print("\n1️⃣ Checking package runners...")
uv_path = shutil.which("uv")
uvx_path = shutil.which("uvx")
print(f"{'✅' if uv_path else '❌'} uv: {uv_path or 'not found'}")
print(f"{'✅' if uvx_path else '❌'} uvx: {uvx_path or 'not found'}")

if uv_path:
    version = run([uv_path, "--version"])
    if version.returncode == 0:
        print(f"   {version.stdout.strip()}")

print("\n2️⃣ Checking the locked development environment...")
if not uv_path:
    print("❌ Install uv, then run: uv sync --locked --extra dev")
else:
    python_check = run([uv_path, "run", "--locked", "python", "--version"])
    if python_check.returncode == 0:
        print(f"✅ {python_check.stdout.strip()}")
    else:
        print("❌ The locked project environment could not start")
        print(python_check.stderr.strip())

print("\n3️⃣ Checking the installed package and MCP registrations...")
inspection = """
import asyncio
from osm_edit_mcp.server import mcp

async def inspect_server():
    print(f"Server: {mcp.name}")
    print(f"Tools: {len(await mcp.list_tools())}")
    print(f"Prompts: {len(await mcp.list_prompts())}")
    print(f"Resource templates: {len(await mcp.list_resource_templates())}")

asyncio.run(inspect_server())
"""
if not uv_path:
    print("❌ Cannot inspect the package without uv")
else:
    package_check = run(
        [uv_path, "run", "--locked", "python", "-c", inspection]
    )
    if package_check.returncode == 0:
        print("✅ Package imports and FastMCP initializes")
        print(package_check.stdout.strip())
    else:
        print("❌ Package initialization failed")
        print(package_check.stderr.strip())

print("\n4️⃣ Recommended Cursor configuration (released package):")
released_config = {
    "mcpServers": {
        "osm-edit": {
            "command": "uvx",
            "args": ["osm-edit-mcp"],
            "env": SAFE_ENV,
        }
    }
}
print("```json")
print(json.dumps(released_config, indent=2))
print("```")

print("\n5️⃣ Local-checkout configuration (unreleased changes):")
local_config = {
    "mcpServers": {
        "osm-edit-local": {
            "command": "uv",
            "args": [
                "run",
                "--locked",
                "--project",
                str(PROJECT_ROOT),
                "osm-edit-mcp",
            ],
            "env": SAFE_ENV,
        }
    }
}
print("```json")
print(json.dumps(local_config, indent=2))
print("```")

print("\n6️⃣ Troubleshooting steps:")
print("1. Run: uv sync --locked --extra dev")
print("2. Restart Cursor after changing its MCP configuration")
print("3. Check Cursor logs: View → Output → MCP")
print("4. If Cursor cannot find uvx, use the path printed in step 1")
print("5. Keep credentials and tokens out of shared logs")

print("\n7️⃣ Inspect the MCP protocol interactively:")
print("npx -y @modelcontextprotocol/inspector uvx osm-edit-mcp")
