#!/usr/bin/env python3
"""
OSM Edit MCP Server - Setup Status Check
========================================

Quick verification script to check if your setup is complete and working.

Usage:
    python status_check.py
"""

import os
import json
from dotenv import load_dotenv

def check_setup_status():
    """Quick status check for OSM Edit MCP Server setup"""
    load_dotenv()

    print("🔍 OSM Edit MCP Server - Setup Status Check")
    print("=" * 50)

    # Check environment file
    if os.path.exists('.env'):
        print("✅ .env file exists")
    else:
        print("❌ .env file missing - copy from .env.example")
        return

    # Check API mode
    use_dev = os.getenv('OSM_USE_DEV_API', 'true').lower() == 'true'
    print(f"✅ API Mode: {'Development' if use_dev else 'Production'}")

    # Check OAuth credentials
    if use_dev:
        client_id = os.getenv('OSM_DEV_CLIENT_ID')
        client_secret = os.getenv('OSM_DEV_CLIENT_SECRET')
        print(f"✅ Dev OAuth ID: {'Set' if client_id else '❌ Missing'}")
        print(f"✅ Dev OAuth Secret: {'Set' if client_secret else '❌ Missing'}")
    else:
        client_id = os.getenv('OSM_PROD_CLIENT_ID')
        client_secret = os.getenv('OSM_PROD_CLIENT_SECRET')
        print(f"✅ Prod OAuth ID: {'Set' if client_id else '❌ Missing'}")
        print(f"✅ Prod OAuth Secret: {'Set' if client_secret else '❌ Missing'}")

    # Check authentication token
    token_file = '.osm_token_dev.json' if use_dev else '.osm_token_prod.json'
    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                token_data = json.load(f)
            print(f"✅ Authentication: Token saved for user ID {token_data.get('user_id', 'unknown')}")
            print(f"   Username: {token_data.get('username', 'unknown')}")
            print(f"   Token expires: {token_data.get('expires_at', 'unknown')}")
        except Exception as e:
            print(f"❌ Authentication: Token file corrupted - {e}")
    else:
        print("❌ Authentication: No token found - run 'python oauth_auth.py'")

    # Check if server files exist
    server_files = [
        'src/osm_edit_mcp/server.py',
        'main.py',
        'test_comprehensive.py',
        'oauth_auth.py'
    ]

    missing_files = []
    for file in server_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            missing_files.append(file)
            print(f"❌ {file} missing")

    print("\n🎯 Next Steps:")
    if not os.path.exists('.env'):
        print("1. Copy .env.example to .env")
    elif missing_files:
        print("1. Restore missing files from repository")
    elif not client_id or not client_secret:
        print("1. Set up OAuth credentials (see README setup guide)")
    elif not os.path.exists(token_file):
        print("1. Run authentication: python oauth_auth.py")
    else:
        print("1. ✅ Setup complete! Run: python test_comprehensive.py")
        print("2. ✅ Start server: python main.py")
        print("3. ✅ Check your changesets: https://api06.dev.openstreetmap.org/user/[username]/history")

if __name__ == "__main__":
    check_setup_status()