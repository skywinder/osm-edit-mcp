# MCP Client Setup Guide

This guide shows how to use OSM Edit MCP Server with various MCP clients.

## 📋 Table of Contents

- [Cursor IDE](#cursor-ide)
- [Claude Desktop](#claude-desktop)
- [Continue.dev](#continuedev)
- [Cline (VSCode)](#cline-vscode)
- [Generic MCP Client](#generic-mcp-client)

## 🎯 Cursor IDE

### Setup Instructions

1. Open Cursor Settings (⌘/Ctrl + ,)
2. Search for "MCP" or go to Features → MCP
3. Add server configuration:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["/absolute/path/to/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/osm-edit-mcp"
      }
    }
  }
}
```

### Alternative: Using Cursor Config File

Edit `~/.cursor/config/mcp.json`:

```json
{
  "servers": {
    "osm-edit": {
      "command": "python",
      "args": ["/Users/YOUR_USERNAME/osm-edit-mcp/main.py"],
      "enabled": true
    }
  }
}
```

### Usage in Cursor

Once configured, you can use natural language:

```
"Find restaurants near Times Square"
"What amenities are within 500m of 51.5074, -0.1278?"
"Search for coffee shops in Seattle"
```

### Troubleshooting Cursor

- Ensure Python path is correct
- Check Cursor logs: View → Output → MCP
- Restart Cursor after configuration changes

## 🖥️ Claude Desktop

### Setup Instructions

1. Locate Claude Desktop config:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Edit the configuration:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["/absolute/path/to/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/osm-edit-mcp",
        "OSM_USE_DEV_API": "true"
      }
    }
  }
}
```

### With Virtual Environment

If using a virtual environment:

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "/path/to/osm-edit-mcp/.venv/bin/python",
      "args": ["/path/to/osm-edit-mcp/main.py"]
    }
  }
}
```

### Windows Configuration

```json
{
  "mcpServers": {
    "osm-edit": {
      "command": "C:\\Python311\\python.exe",
      "args": ["C:\\Users\\USERNAME\\osm-edit-mcp\\main.py"],
      "env": {
        "PYTHONPATH": "C:\\Users\\USERNAME\\osm-edit-mcp"
      }
    }
  }
}
```

## 🔄 Continue.dev

### Setup Instructions

1. Open Continue settings
2. Add to `~/.continue/config.json`:

```json
{
  "models": [...],
  "mcpServers": [
    {
      "name": "osm-edit",
      "command": "python",
      "args": ["/path/to/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "/path/to/osm-edit-mcp"
      }
    }
  ]
}
```

### Usage Example

```
@mcp What restaurants are near latitude 40.7580, longitude -73.9855?
@mcp Find hospitals within 1km of Central Park
```

## 🆚 Cline (VSCode)

### Setup Instructions

1. Install Cline extension in VSCode
2. Open VSCode settings (Code → Preferences → Settings)
3. Search for "Cline MCP"
4. Add configuration:

```json
{
  "cline.mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["${workspaceFolder}/osm-edit-mcp/main.py"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}/osm-edit-mcp"
      }
    }
  }
}
```

### Alternative: Workspace Settings

Create `.vscode/settings.json` in your project:

```json
{
  "cline.mcpServers": {
    "osm-edit": {
      "command": "python",
      "args": ["./osm-edit-mcp/main.py"],
      "enabled": true
    }
  }
}
```

## 🔧 Generic MCP Client

### Basic Configuration

Most MCP clients follow a similar pattern:

```json
{
  "servers": {
    "osm-edit": {
      "command": "python",
      "args": ["/path/to/main.py"],
      "env": {
        "PYTHONPATH": "/path/to/osm-edit-mcp",
        "OSM_USE_DEV_API": "true",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Using NPX (Node.js)

Some clients support NPX execution:

```json
{
  "osm-edit": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-osm-edit"]
  }
}
```

## 🐳 Docker Configuration

For clients that support Docker:

```json
{
  "servers": {
    "osm-edit": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file", ".env",
        "osm-edit-mcp:latest"
      ]
    }
  }
}
```

## ⚙️ Environment Variables

You can pass environment variables through the client:

```json
{
  "env": {
    "OSM_USE_DEV_API": "true",
    "OSM_DEV_CLIENT_ID": "your_client_id",
    "OSM_DEV_CLIENT_SECRET": "your_client_secret",
    "LOG_LEVEL": "DEBUG",
    "PYTHONPATH": "/path/to/osm-edit-mcp"
  }
}
```

## 🧪 Testing Your Setup

### 1. Check Server is Running

Most clients show server status. Look for:
- Green indicator next to "osm-edit"
- No error messages in logs
- Server responding to requests

### 2. Test Basic Command

Try these in your client:

```
"What MCP tools are available?"
"Get server info"
"Validate coordinates 51.5074, -0.1278"
```

### 3. View Logs

- **Cursor**: View → Output → MCP
- **VSCode**: Output panel → Cline
- **Claude Desktop**: Check system logs
- **Continue**: View logs in settings

## 🚨 Common Issues

### Issue: "Command not found"

**Solution**: Use absolute paths

```json
{
  "command": "/usr/bin/python3",
  "args": ["/home/user/osm-edit-mcp/main.py"]
}
```

### Issue: "Module not found"

**Solution**: Set PYTHONPATH

```json
{
  "env": {
    "PYTHONPATH": "/path/to/osm-edit-mcp:$PYTHONPATH"
  }
}
```

### Issue: "Permission denied"

**Solution**: Make script executable

```bash
chmod +x /path/to/osm-edit-mcp/main.py
```

### Issue: "Server not responding"

**Solution**: Check Python dependencies

```bash
cd /path/to/osm-edit-mcp
pip install -r requirements.txt
```

## 📝 Example Queries

Once configured, try these queries in your MCP client:

### Basic Searches
- "Find Italian restaurants near the Colosseum"
- "What's at coordinates 40.7580, -73.9855?"
- "Search for hospitals in downtown Seattle"

### Area Exploration
- "What amenities are within 500m of Big Ben?"
- "Find all cafes in Central Park area"
- "List tourist attractions near Eiffel Tower"

### Validation
- "Validate these coordinates: 51.5074, -0.1278"
- "Is 91.0, 181.0 a valid coordinate?"
- "Get location info for 48.8584, 2.2945"

### Natural Language
- "Add a coffee shop called Bean There at 44.8, 20.5"
- "Find places to eat lunch near Times Square"
- "What museums are near my location?"

## 🔗 Additional Resources

- [MCP Specification](https://modelcontextprotocol.io/docs)
- [OSM Edit MCP Docs](../README.md)
- [Troubleshooting Guide](../README.md#-troubleshooting)

## 💡 Tips

1. **Use absolute paths** to avoid path resolution issues
2. **Check logs** when debugging connection problems
3. **Test with simple queries** first before complex operations
4. **Enable debug logging** when troubleshooting:
   ```json
   "env": {
     "LOG_LEVEL": "DEBUG"
   }
   ```

---

Need help? Open an issue on [GitHub](https://github.com/skywinder/osm-edit-mcp/issues)!