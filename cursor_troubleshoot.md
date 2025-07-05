# Cursor MCP Integration Troubleshooting

## Issue: "0 tools enabled" in Cursor

### 1. Update Your Cursor Configuration

Replace your current configuration with this exact JSON:

```json
{
  "osm-edit": {
    "command": "uv",
    "args": ["run", "python", "/Users/pk/repo/_mine/osm-edit-mcp/main.py"],
    "cwd": "/Users/pk/repo/_mine/osm-edit-mcp",
    "env": {
      "PYTHONPATH": "/Users/pk/repo/_mine/osm-edit-mcp/src"
    }
  }
}
```

### 2. Alternative Configurations

If the above doesn't work, try these alternatives:

**Option A - Using absolute uv path:**
```json
{
  "osm-edit": {
    "command": "/opt/homebrew/bin/uv",
    "args": ["run", "python", "main.py"],
    "cwd": "/Users/pk/repo/_mine/osm-edit-mcp"
  }
}
```

**Option B - Direct Python (without uv):**
```json
{
  "osm-edit": {
    "command": "python",
    "args": ["/Users/pk/repo/_mine/osm-edit-mcp/main.py"],
    "cwd": "/Users/pk/repo/_mine/osm-edit-mcp",
    "env": {
      "PYTHONPATH": "/Users/pk/repo/_mine/osm-edit-mcp/src"
    }
  }
}
```

### 3. Debugging Steps

1. **Check Cursor MCP Logs**:
   - View → Output → Select "MCP" from dropdown
   - Look for error messages when Cursor tries to start the server

2. **Verify Dependencies**:
   ```bash
   cd /Users/pk/repo/_mine/osm-edit-mcp
   uv sync
   ```

3. **Test Server Manually**:
   ```bash
   cd /Users/pk/repo/_mine/osm-edit-mcp
   echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"1.0.0","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}' | uv run python main.py
   ```
   
   You should see a JSON response with "serverInfo" if working correctly.

4. **Restart Cursor**:
   - After changing configuration, fully quit and restart Cursor
   - Sometimes Cursor caches MCP server states

### 4. Common Issues

1. **Path Issues**:
   - Make sure all paths are absolute (starting with /)
   - The `args` array should have absolute path to main.py

2. **Python Environment**:
   - The PYTHONPATH env variable helps find the src modules
   - Make sure you've run `uv sync` in the project directory

3. **Permissions**:
   - Check that main.py is readable: `ls -la /Users/pk/repo/_mine/osm-edit-mcp/main.py`

### 5. What Success Looks Like

When properly configured, you should see:
- Green dot next to "osm-edit" in Cursor's MCP panel
- "25 tools enabled" (or similar number)
- Tools like "find_nearby_amenities", "get_place_info" available

### 6. If Still Not Working

Run the debug script and share the output:
```bash
cd /Users/pk/repo/_mine/osm-edit-mcp
uv run python debug_mcp_cursor.py
```

Also check Cursor's MCP output logs and share any error messages.