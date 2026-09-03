#!/bin/bash
# Install script for OSM Edit MCP Server using uv

set -euo pipefail

echo "🚀 OSM Edit MCP Server - Installation with uv"
echo "============================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Installing now..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv &> /dev/null; then
        echo "❌ uv installation finished, but the uv executable was not found"
        echo "   Open a new shell or add ~/.local/bin to PATH, then retry."
        exit 1
    fi

    echo "✅ uv installed successfully!"
else
    echo "✅ uv is already installed"
fi

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3.10 or higher is required, but python3 was not found"
    exit 1
fi

python_version=$(python3 --version 2>&1 | awk '{print $2}')
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "❌ Python 3.10 or higher is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Install dependencies
echo "📦 Installing dependencies with uv..."
uv sync --locked --extra dev

# Create a private .env from the public template if it does not exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    install -m 600 .env.example .env
    echo "✅ .env file created"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Run status check: uv run --locked python status_check.py"
echo "2. Export dotenv path: export OSM_EDIT_MCP_ENV_FILE=\"$PWD/.env\""
echo "3. Start server through an MCP host with: uv run --locked osm-edit-mcp"
echo "4. For write operations, see README for OAuth setup"
