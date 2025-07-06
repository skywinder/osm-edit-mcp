#!/bin/bash
# OSM Edit MCP Server Deployment Script

set -e

echo "🚀 OSM Edit MCP Server Deployment Script"
echo "========================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your actual credentials before proceeding."
    echo "   You need to set:"
    echo "   - OSM_DEV_CLIENT_ID and OSM_DEV_CLIENT_SECRET"
    echo "   - API_KEY (for web server authentication)"
    echo ""
    read -p "Press Enter after you've updated .env file..."
fi

# Generate SSL certificates for development
if [ ! -d "ssl" ]; then
    echo "🔐 Generating self-signed SSL certificates for development..."
    mkdir -p ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ssl/key.pem -out ssl/cert.pem \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
fi

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check service health
echo "🏥 Checking service health..."
if curl -k -s https://localhost/health > /dev/null; then
    echo "✅ Services are running!"
    echo ""
    echo "🌐 Access your OSM Edit MCP Server at:"
    echo "   - HTTPS: https://localhost (with Nginx)"
    echo "   - HTTP: http://localhost:8000 (direct)"
    echo ""
    echo "📚 API Documentation: http://localhost:8000/docs"
    echo ""
    echo "🔑 Remember to use your API_KEY in the Authorization header:"
    echo "   Authorization: Bearer your-api-key-here"
else
    echo "❌ Service health check failed!"
    echo "Check logs with: docker-compose logs"
    exit 1
fi

echo ""
echo "📋 Useful commands:"
echo "   - View logs: docker-compose logs -f"
echo "   - Stop services: docker-compose down"
echo "   - Restart services: docker-compose restart"
echo "   - Update and restart: git pull && docker-compose build && docker-compose up -d"