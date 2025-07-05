#!/bin/bash
# OSM Edit MCP Server Manager Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/.osm-mcp.pid"
LOG_FILE="$PROJECT_DIR/osm-mcp.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if server is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            # PID file exists but process is not running
            rm "$PID_FILE"
        fi
    fi
    return 1
}

# Function to start the server
start_server() {
    if is_running; then
        echo -e "${YELLOW}Server is already running with PID $(cat "$PID_FILE")${NC}"
        return 1
    fi
    
    echo -e "${GREEN}Starting OSM Edit MCP Server...${NC}"
    cd "$PROJECT_DIR"
    
    # Check if uv is available
    if command -v uv &> /dev/null; then
        nohup uv run python main.py > "$LOG_FILE" 2>&1 &
    else
        nohup python main.py > "$LOG_FILE" 2>&1 &
    fi
    
    PID=$!
    echo $PID > "$PID_FILE"
    
    # Wait a moment and check if it started successfully
    sleep 2
    if is_running; then
        echo -e "${GREEN}✅ Server started successfully (PID: $PID)${NC}"
        echo -e "${GREEN}📄 Logs: $LOG_FILE${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed to start server${NC}"
        echo -e "${RED}Check logs at: $LOG_FILE${NC}"
        return 1
    fi
}

# Function to stop the server
stop_server() {
    if ! is_running; then
        echo -e "${YELLOW}Server is not running${NC}"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    echo -e "${GREEN}Stopping OSM Edit MCP Server (PID: $PID)...${NC}"
    
    kill "$PID"
    
    # Wait for process to stop
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            rm -f "$PID_FILE"
            echo -e "${GREEN}✅ Server stopped successfully${NC}"
            return 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    echo -e "${YELLOW}Force stopping server...${NC}"
    kill -9 "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    echo -e "${GREEN}✅ Server stopped${NC}"
}

# Function to restart the server
restart_server() {
    echo -e "${GREEN}Restarting OSM Edit MCP Server...${NC}"
    stop_server
    sleep 2
    start_server
}

# Function to show server status
status_server() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}✅ Server is running (PID: $PID)${NC}"
        
        # Show process info
        ps -p "$PID" -o pid,vsz,rss,comm
        
        # Show last few log lines
        if [ -f "$LOG_FILE" ]; then
            echo -e "\n${GREEN}Recent logs:${NC}"
            tail -5 "$LOG_FILE"
        fi
    else
        echo -e "${RED}❌ Server is not running${NC}"
    fi
}

# Function to show logs
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo -e "${GREEN}Following logs (Ctrl+C to stop)...${NC}"
        tail -f "$LOG_FILE"
    else
        echo -e "${RED}No log file found at: $LOG_FILE${NC}"
    fi
}

# Main script logic
case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        status_server
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "OSM Edit MCP Server Manager"
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the server in background"
        echo "  stop     - Stop the server"
        echo "  restart  - Restart the server"
        echo "  status   - Show server status"
        echo "  logs     - Follow server logs"
        exit 1
        ;;
esac

exit $?