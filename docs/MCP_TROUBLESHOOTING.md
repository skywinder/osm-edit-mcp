# MCP Client Troubleshooting Guide

## 🔍 Diagnosing Connection Issues

### 1. Test Server Directly

First, verify the server works standalone:

```bash
cd /path/to/osm-edit-mcp
python main.py
```

You should see:
```
OSM Edit MCP Server v0.1.0
API Mode: Development
Starting OSM Edit MCP Server...
```

If this fails, fix server issues first.

### 2. Check Client Logs

#### Cursor
- View → Output → Select "MCP" from dropdown
- Look for connection errors or Python exceptions

#### Claude Desktop
- macOS: `~/Library/Logs/Claude/mcp.log`
- Windows: `%LOCALAPPDATA%\Claude\logs\mcp.log`

#### VSCode (Cline)
- Output panel → Select "Cline" or "MCP"
- Developer Tools: Help → Toggle Developer Tools → Console

#### Continue.dev
- Click gear icon → View Logs
- Check `~/.continue/logs/`

### 3. Common Error Messages

#### "Command not found: python"

**Problem**: Python not in PATH or wrong command

**Solutions**:
```json
// Try python3
"command": "python3"

// Use full path
"command": "/usr/bin/python3"

// Windows
"command": "C:\\Python311\\python.exe"
```

#### "ModuleNotFoundError: No module named 'mcp'"

**Problem**: Dependencies not installed

**Solution**:
```bash
cd /path/to/osm-edit-mcp
pip install -r requirements.txt
```

#### "No module named 'osm_edit_mcp'"

**Problem**: PYTHONPATH not set correctly

**Solution**:
```json
"env": {
  "PYTHONPATH": "/absolute/path/to/osm-edit-mcp"
}
```

#### "Permission denied"

**Problem**: Script not executable

**Solution**:
```bash
chmod +x /path/to/osm-edit-mcp/main.py
```

#### "Connection refused" or "Server not responding"

**Problem**: Server crashed or not starting

**Debug steps**:
1. Run server manually and check for errors
2. Check Python version (needs 3.10+)
3. Verify all dependencies installed
4. Check .env file exists

## 🧪 Testing Tools

### Quick Connection Test

Create `test_mcp.py`:

```python
import asyncio
from src.osm_edit_mcp.server import get_server_info

async def test():
    result = await get_server_info()
    print(f"Server response: {result}")

asyncio.run(test())
```

Run: `python test_mcp.py`

### MCP Protocol Test

Some clients support testing:

```bash
# Test with MCP CLI (if available)
mcp test /path/to/osm-edit-mcp/main.py

# Test with npx
npx @modelcontextprotocol/cli test python /path/to/main.py
```

## 🔧 Platform-Specific Issues

### macOS

**Issue**: "xcrun: error: invalid active developer path"

**Solution**: Install Xcode Command Line Tools
```bash
xcode-select --install
```

**Issue**: Python SSL certificate errors

**Solution**:
```bash
pip install --upgrade certifi
```

### Windows

**Issue**: Path separators in config

**Solution**: Use forward slashes or escape backslashes
```json
// Good
"args": ["C:/Users/Name/osm-edit-mcp/main.py"]

// Also good
"args": ["C:\\Users\\Name\\osm-edit-mcp\\main.py"]
```

**Issue**: Virtual environment not activating

**Solution**: Use full path to venv Python
```json
"command": "C:/path/to/osm-edit-mcp/.venv/Scripts/python.exe"
```

### Linux

**Issue**: Python version conflicts

**Solution**: Specify exact Python version
```json
"command": "/usr/bin/python3.11"
```

## 📋 Debug Checklist

- [ ] Server runs standalone without errors
- [ ] Python version is 3.10 or higher
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Using absolute paths in configuration
- [ ] PYTHONPATH includes project directory
- [ ] .env file exists (even if empty)
- [ ] No syntax errors in client config JSON
- [ ] Client has permissions to execute Python
- [ ] No firewall blocking local connections
- [ ] Restarted client after config changes

## 🚀 Working Configurations

### Minimal Working Config
```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["/absolute/path/to/main.py"]
    }
  }
}
```

### Full Debug Config
```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "/usr/bin/python3",
      "args": ["/home/user/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "/home/user/osm-edit-mcp",
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "DEBUG",
        "PYTHONUNBUFFERED": "1"
      },
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

## 💡 Pro Tips

1. **Always use absolute paths** - Relative paths often fail
2. **Test incrementally** - Start with minimal config
3. **Check client version** - Ensure MCP support is available
4. **Use debug logging** - Set `LOG_LEVEL=DEBUG`
5. **Monitor both logs** - Check client AND server logs

## 🆘 Still Having Issues?

1. Run the diagnostic script:
   ```bash
   python status_check.py
   ```

2. Collect debug info:
   - Client name and version
   - Operating system
   - Python version (`python --version`)
   - Error messages from logs
   - Your configuration (remove secrets)

3. Open an issue: https://github.com/skywinder/osm-edit-mcp/issues

Include all debug info for fastest resolution!