#!/bin/bash
# OSM Edit MCP Server Deployment Script

set -eu

echo "🚀 OSM Edit MCP Server Deployment Script"
echo "========================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Prefer the current Docker Compose plugin, while retaining compatibility with
# hosts that still provide the standalone docker-compose command.
if docker compose version > /dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose &> /dev/null; then
    COMPOSE=(docker-compose)
else
    echo "❌ Docker Compose is not installed. Please install it first."
    exit 1
fi
COMPOSE_DISPLAY="${COMPOSE[*]}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    install -m 600 .env.example .env
    echo "⚠️  Please edit .env file with your actual credentials before proceeding."
    echo "   You need to set:"
    echo "   - OSM_DEV_CLIENT_ID and OSM_DEV_CLIENT_SECRET"
    echo "   - API_KEY (for web server authentication)"
    echo ""
    read -p "Press Enter after you've updated .env file..."
fi

# Build and start the loopback-bound read-only HTTP wrapper. The Nginx service
# remains an explicit remote-read-only profile and is not exposed by default.
echo "🔨 Building Docker images..."
"${COMPOSE[@]}" build osm-edit-mcp

echo "🚀 Starting loopback service..."
"${COMPOSE[@]}" up -d osm-edit-mcp

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
healthy=false
for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:8000/health > /dev/null 2>&1; then
        healthy=true
        break
    fi
    sleep 1
done

# Check service health
echo "🏥 Checking service health..."
if [ "$healthy" = true ]; then
    echo "✅ Services are running!"
    echo ""
    echo "🌐 Access your OSM Edit MCP Server at:"
    echo "   - HTTP: http://127.0.0.1:8000"
    echo ""
    echo "📚 API Documentation: http://127.0.0.1:8000/docs"
    echo ""
    echo "🔑 Remember to use your API_KEY in the Authorization header:"
    echo "   Authorization: Bearer your-api-key-here"
else
    echo "❌ Service health check failed!"
    echo "Check logs with: $COMPOSE_DISPLAY logs osm-edit-mcp"
    exit 1
fi

echo ""
echo "📋 Useful commands:"
echo "   - View logs: $COMPOSE_DISPLAY logs -f osm-edit-mcp"
echo "   - Stop services: $COMPOSE_DISPLAY down"
echo "   - Restart services: $COMPOSE_DISPLAY restart osm-edit-mcp"
echo "   - Update and restart: git pull && $COMPOSE_DISPLAY up -d --build osm-edit-mcp"
