#!/usr/bin/env python3
"""
Debug script to help troubleshoot MCP server issues in Cursor
"""

import sys
import json
import subprocess
from pathlib import Path

print("🔍 MCP Server Debug Tool for Cursor")
print("=" * 50)

# 1. Check if the server can be imported
print("\n1️⃣ Checking if server can be imported...")
sys.path.insert(0, str(Path(__file__).parent / "src"))
try:
    from osm_edit_mcp.server import mcp
    print("✅ Server imported successfully")
    print(f"   Name: {mcp.name}")
    # FastMCP doesn't expose tools directly, but we know they exist
    print("   Tools are registered with FastMCP")
except Exception as e:
    print(f"❌ Failed to import server: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. Check if uv is available
print("\n2️⃣ Checking if uv is available...")
try:
    result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ uv is installed: {result.stdout.strip()}")
    else:
        print("❌ uv command failed")
except FileNotFoundError:
    print("❌ uv is not installed or not in PATH")
    print("   Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")

# 3. Check Python path
print("\n3️⃣ Checking Python environment...")
try:
    result = subprocess.run(["uv", "run", "python", "--version"], 
                          capture_output=True, text=True, 
                          cwd=Path(__file__).parent)
    if result.returncode == 0:
        print(f"✅ Python via uv: {result.stdout.strip()}")
    else:
        print(f"❌ Failed to run Python via uv: {result.stderr}")
except Exception as e:
    print(f"❌ Error checking Python: {e}")

# 4. Test MCP server initialization
print("\n4️⃣ Testing MCP server initialization...")
test_script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from osm_edit_mcp.server import mcp
print(f"Server: {mcp.name}")
print("Tools registered")
'''

try:
    result = subprocess.run(
        ["uv", "run", "python", "-c", test_script],
        capture_output=True, text=True,
        cwd=Path(__file__).parent
    )
    if result.returncode == 0:
        print("✅ Server initializes correctly via uv")
        print(f"   {result.stdout.strip()}")
    else:
        print("❌ Server initialization failed")
        print(f"   Error: {result.stderr}")
except Exception as e:
    print(f"❌ Failed to test initialization: {e}")

# 5. Generate correct Cursor configuration
print("\n5️⃣ Correct Cursor Configuration:")
cursor_config = {
    "osm-edit": {
        "command": "uv",
        "args": ["run", "python", str(Path(__file__).parent / "main.py")],
        "cwd": str(Path(__file__).parent),
        "env": {
            "PYTHONPATH": str(Path(__file__).parent / "src")
        }
    }
}

print("```json")
print(json.dumps(cursor_config, indent=2))
print("```")

# 6. Alternative configurations
print("\n6️⃣ Alternative Configurations to Try:")

# Without uv
print("\nOption A - Direct Python:")
alt_config1 = {
    "osm-edit": {
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "main.py")],
        "cwd": str(Path(__file__).parent),
        "env": {
            "PYTHONPATH": str(Path(__file__).parent / "src")
        }
    }
}
print("```json")
print(json.dumps(alt_config1, indent=2))
print("```")

# With absolute path to uv
print("\nOption B - Absolute uv path:")
uv_path = subprocess.run(["which", "uv"], capture_output=True, text=True).stdout.strip()
if uv_path:
    alt_config2 = {
        "osm-edit": {
            "command": uv_path,
            "args": ["run", "python", "main.py"],
            "cwd": str(Path(__file__).parent)
        }
    }
    print("```json")
    print(json.dumps(alt_config2, indent=2))
    print("```")

print("\n7️⃣ Troubleshooting Steps:")
print("1. Restart Cursor after changing configuration")
print("2. Check Cursor logs: View → Output → MCP")
print("3. Try the alternative configurations above")
print("4. Make sure all dependencies are installed: uv sync")
print("5. Check if .env file exists with proper configuration")

print("\n8️⃣ Testing MCP Protocol:")
print("Run this to simulate MCP communication:")
print(f"echo '{{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":1}}' | uv run python {Path(__file__).parent / 'main.py'}")