# Running the OSM Edit MCP Server

## ⚠️ Important: Understanding MCP Servers

**MCP servers are NOT standalone HTTP servers!** They communicate via stdin/stdout with MCP clients. When you run `python main.py` directly, it will appear to "hang" because it's waiting for input from an MCP client.

### How MCP Works:
1. MCP clients (Cursor, Claude Desktop, etc.) start the server as a subprocess
2. Communication happens through stdin/stdout using JSON-RPC
3. The server doesn't listen on any network port

### To Test the Server:
- ✅ Use `python test_comprehensive.py` to test functionality
- ✅ Use `python quick_test.py` for a quick test
- ✅ Configure in an MCP client (see MCP_CLIENT_SETUP.md)
- ❌ Don't run `python main.py` directly expecting a web interface

## 🔍 Check if Server is Already Running

### Method 1: Check Process
```bash
# Check if python process is running main.py
ps aux | grep "[m]ain.py"

# Or check for the server name
ps aux | grep "[o]sm-edit-mcp"
```

### Method 2: Check MCP Port (if configured)
```bash
# Default MCP servers often use stdio, but if using TCP:
lsof -i :PORT_NUMBER
```

### Method 3: Check in your MCP Client
- **Cursor**: Look for green dot next to "osm-edit" in MCP panel
- **Claude Desktop**: Check server status in logs
- **VSCode/Cline**: View → Output → Select MCP

## 🏃 Running in Background

### Option 1: Using nohup (Simple)
```bash
# Start in background with nohup
nohup uv run python main.py > osm-mcp.log 2>&1 &

# Or with pip
nohup python main.py > osm-mcp.log 2>&1 &

# Get the process ID
echo $!

# View logs
tail -f osm-mcp.log
```

### Option 2: Using screen (Recommended)
```bash
# Install screen if needed
# Ubuntu/Debian: sudo apt-get install screen
# macOS: brew install screen

# Start a new screen session
screen -S osm-mcp

# Run the server
uv run python main.py

# Detach from screen: Press Ctrl+A, then D

# List screen sessions
screen -ls

# Reattach to session
screen -r osm-mcp

# Kill the session
screen -X -S osm-mcp quit
```

### Option 3: Using tmux (Advanced)
```bash
# Install tmux if needed
# Ubuntu/Debian: sudo apt-get install tmux
# macOS: brew install tmux

# Start new tmux session
tmux new -s osm-mcp

# Run the server
uv run python main.py

# Detach: Press Ctrl+B, then D

# List sessions
tmux ls

# Reattach
tmux attach -t osm-mcp

# Kill session
tmux kill-session -t osm-mcp
```

### Option 4: Using systemd (Linux Production)

Create `/etc/systemd/system/osm-mcp.service`:

```ini
[Unit]
Description=OSM Edit MCP Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/osm-edit-mcp
Environment="PATH=/home/YOUR_USERNAME/.local/bin:/usr/bin"
ExecStart=/usr/bin/python /path/to/osm-edit-mcp/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Start service
sudo systemctl start osm-mcp

# Enable on boot
sudo systemctl enable osm-mcp

# Check status
sudo systemctl status osm-mcp

# View logs
sudo journalctl -u osm-mcp -f
```

### Option 5: Using pm2 (Node.js Process Manager)
```bash
# Install pm2
npm install -g pm2

# Start with pm2
pm2 start "uv run python main.py" --name osm-mcp

# Or create ecosystem file
echo 'module.exports = {
  apps: [{
    name: "osm-mcp",
    script: "python",
    args: "main.py",
    cwd: "/path/to/osm-edit-mcp",
    interpreter: "uv run"
  }]
}' > ecosystem.config.js

pm2 start ecosystem.config.js

# List processes
pm2 list

# View logs
pm2 logs osm-mcp

# Stop
pm2 stop osm-mcp

# Restart
pm2 restart osm-mcp
```

## 🛑 Stopping the Server

### Find and Kill Process
```bash
# Find the process
ps aux | grep "[m]ain.py"

# Kill by process ID
kill PID

# Force kill if needed
kill -9 PID

# Kill all Python processes running main.py
pkill -f "python.*main.py"
```

### Using Process Managers
```bash
# Screen
screen -X -S osm-mcp quit

# Tmux
tmux kill-session -t osm-mcp

# Systemd
sudo systemctl stop osm-mcp

# PM2
pm2 stop osm-mcp
```

## 📊 Monitoring the Server

### Watch Logs in Real-time
```bash
# If using log file
tail -f osm-mcp.log

# If using systemd
sudo journalctl -u osm-mcp -f

# If using pm2
pm2 logs osm-mcp
```

### Check Server Health
```bash
# Create a health check script
cat > check_health.py << 'EOF'
import asyncio
from src.osm_edit_mcp.server import get_server_info

async def check():
    try:
        result = await get_server_info()
        print("✅ Server is healthy:", result['success'])
    except Exception as e:
        print("❌ Server error:", e)

asyncio.run(check())
EOF

# Run health check
uv run python check_health.py
```

## 🔄 Auto-restart on Crash

### Using a Simple Bash Script
```bash
#!/bin/bash
# save as run_server.sh

while true; do
    echo "Starting OSM MCP Server..."
    uv run python main.py
    
    # If server exits, wait before restarting
    echo "Server stopped. Restarting in 5 seconds..."
    sleep 5
done
```

Make it executable and run:
```bash
chmod +x run_server.sh
nohup ./run_server.sh > osm-mcp.log 2>&1 &
```

## 🎯 Best Practices

1. **Development**: Use `screen` or `tmux` for easy access
2. **Production**: Use `systemd` (Linux) or `pm2` for reliability
3. **Logging**: Always redirect output to a log file
4. **Monitoring**: Set up health checks
5. **Auto-restart**: Use process managers that handle crashes

## 🚨 Troubleshooting

### Server Won't Start in Background
- Check if another instance is already running
- Verify Python path is correct
- Ensure all dependencies are installed
- Check log files for errors

### Can't Connect from MCP Client
- Verify server is actually running (`ps aux | grep main.py`)
- Check client configuration points to correct path
- Ensure no firewall blocking connection
- Try running in foreground first to see errors

### Process Keeps Dying
- Check system resources (memory, CPU)
- Look for Python errors in logs
- Verify all environment variables are set
- Try running with `PYTHONUNBUFFERED=1` for immediate log output