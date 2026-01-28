#!/usr/bin/env python3
"""
OAuth Authentication for OSM Edit MCP Server
============================================

This script helps you authenticate with OpenStreetMap using OAuth 2.0.
Run this to get authentication tokens for use with the MCP server.

Usage:
    python oauth_auth.py              # Development API (default)
    python oauth_auth.py --prod       # Production API
    python oauth_auth.py --dev        # Development API (explicit)
"""

import asyncio
import os
import sys
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
import httpx
from dotenv import load_dotenv
import json
import keyring
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

class OSMOAuth:
    def __init__(self, use_dev_api=True):
        self.use_dev_api = use_dev_api

                # Get OAuth credentials from environment based on dev/prod setting
        if self.use_dev_api:
            self.client_id = os.getenv("OSM_DEV_CLIENT_ID")
            self.client_secret = os.getenv("OSM_DEV_CLIENT_SECRET")
            self.redirect_uri = os.getenv("OSM_DEV_REDIRECT_URI") or "http://localhost:8080/callback"
        else:
            self.client_id = os.getenv("OSM_PROD_CLIENT_ID")
            self.client_secret = os.getenv("OSM_PROD_CLIENT_SECRET")
            self.redirect_uri = os.getenv("OSM_PROD_REDIRECT_URI") or "https://localhost:8080/callback"

        if self.use_dev_api:
            # Development API endpoints
            self.api_base = "https://api06.dev.openstreetmap.org"
            self.auth_url = "https://api06.dev.openstreetmap.org/oauth2/authorize"
            self.token_url = "https://api06.dev.openstreetmap.org/oauth2/token"
        else:
            # Production API endpoints
            self.api_base = "https://api.openstreetmap.org"
            self.auth_url = "https://www.openstreetmap.org/oauth2/authorize"
            self.token_url = "https://www.openstreetmap.org/oauth2/token"

        print(f"🔧 Using {'Development' if self.use_dev_api else 'Production'} API")
        print(f"📡 API Base: {self.api_base}")
        print(f"🔑 Client ID: {self.client_id}")
        print(f"🔄 Redirect URI: {self.redirect_uri}")

    def get_authorization_url(self):
        """Generate the authorization URL for OAuth flow."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read_prefs write_prefs write_api write_changeset_comments",
            "state": "oauth_flow"
        }

        url = f"{self.auth_url}?{urlencode(params)}"
        return url

    async def exchange_code_for_token(self, authorization_code):
        """Exchange authorization code for access token."""
        try:
            data = {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": authorization_code,
                "redirect_uri": self.redirect_uri
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    headers={"Accept": "application/json"}
                )

                if response.status_code == 200:
                    token_data = response.json()

                    # Save token to keyring
                    keyring_service = f"osm-edit-mcp-{'dev' if self.use_dev_api else 'prod'}"
                    keyring.set_password(keyring_service, "access_token", token_data["access_token"])

                    if "refresh_token" in token_data:
                        keyring.set_password(keyring_service, "refresh_token", token_data["refresh_token"])

                    # Also save token data to a file as backup
                    token_file = ".osm_token_dev.json" if self.use_dev_api else ".osm_token_prod.json"
                    with open(token_file, "w") as f:
                        token_data["expires_at"] = (datetime.now() + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat()
                        json.dump(token_data, f, indent=2)

                    print(f"✅ Token saved to keyring and {token_file}")
                    return token_data
                else:
                    print(f"❌ Token exchange failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return None

        except Exception as e:
            print(f"❌ Error during token exchange: {e}")
            return None

    async def test_authentication(self):
        """Test if the current authentication works."""
        try:
            # Get token from keyring
            keyring_service = f"osm-edit-mcp-{'dev' if self.use_dev_api else 'prod'}"
            access_token = keyring.get_password(keyring_service, "access_token")

            if not access_token:
                print("❌ No access token found. Please authenticate first.")
                return False

            # Test API call with authentication
            headers = {"Authorization": f"Bearer {access_token}"}

            async with httpx.AsyncClient() as client:
                # Test with user details endpoint
                response = await client.get(
                    f"{self.api_base}/api/0.6/user/details",
                    headers=headers
                )

                if response.status_code == 200:
                    print("✅ Authentication successful!")

                    # Parse user info from XML
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.text)
                    user = root.find("user")
                    if user is not None:
                        display_name = user.get("display_name")
                        user_id = user.get("id")
                        print(f"👤 Logged in as: {display_name} (ID: {user_id})")

                    return True
                else:
                    print(f"❌ Authentication test failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False

        except Exception as e:
            print(f"❌ Error testing authentication: {e}")
            return False

async def main():
    """Main OAuth authentication flow."""
    print("🚀 OSM Edit MCP Server - OAuth Authentication")
    print("=" * 50)

    # Determine which API to use
    use_dev_api = True  # Default to dev for safety

    # Check command-line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ['--prod', '--production']:
            use_dev_api = False
            print("⚠️  WARNING: Using PRODUCTION API - changes will affect real OSM data!")
        elif sys.argv[1] in ['--dev', '--development']:
            use_dev_api = True
        elif sys.argv[1] in ['-h', '--help']:
            print("Usage:")
            print("  python oauth_auth.py              # Development API (default)")
            print("  python oauth_auth.py --dev        # Development API (explicit)")
            print("  python oauth_auth.py --prod       # Production API")
            print("  python oauth_auth.py --help       # Show this help")
            return
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Use --help for usage information")
            return
    # Check environment variable as fallback
    elif os.getenv("OSM_USE_PROD_API", "").lower() in ["true", "1", "yes"]:
        use_dev_api = False
        print("⚠️  WARNING: Using PRODUCTION API (from OSM_USE_PROD_API env var)")

    # Initialize OAuth
    oauth = OSMOAuth(use_dev_api=use_dev_api)

    if not oauth.client_id or not oauth.client_secret:
        print("❌ Missing OAuth credentials!")
        if use_dev_api:
            print("Please set OSM_DEV_CLIENT_ID and OSM_DEV_CLIENT_SECRET in your .env file")
        else:
            print("Please set OSM_PROD_CLIENT_ID and OSM_PROD_CLIENT_SECRET in your .env file")
        return

    # Test if we already have valid authentication
    print("\n📋 Testing existing authentication...")
    if await oauth.test_authentication():
        print("🎉 You're already authenticated! Ready to use the MCP server.")
        return

    print("\n🔐 Starting OAuth authentication flow...")

    # Step 1: Get authorization URL
    auth_url = oauth.get_authorization_url()
    print(f"\n📝 Step 1: Please visit this URL to authorize the application:")
    print(f"🔗 {auth_url}")

    # Try to open URL in browser
    try:
        webbrowser.open(auth_url)
        print("🌐 Opening browser automatically...")
    except:
        print("⚠️  Could not open browser automatically. Please copy and paste the URL above.")

    print("\n📋 Step 2: After authorizing, you'll be redirected to a URL that starts with:")
    print(f"   {oauth.redirect_uri}?code=...")

    # Get authorization code from user
    print("\n📝 Step 3: Please paste the full redirect URL here:")
    redirect_url = input("Redirect URL: ").strip()

    # Parse authorization code
    try:
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)

        if "code" not in query_params:
            print("❌ No authorization code found in URL")
            return

        authorization_code = query_params["code"][0]
        print(f"✅ Found authorization code: {authorization_code[:20]}...")

    except Exception as e:
        print(f"❌ Error parsing redirect URL: {e}")
        return

    # Step 4: Exchange code for token
    print("\n🔄 Step 4: Exchanging authorization code for access token...")
    token_data = await oauth.exchange_code_for_token(authorization_code)

    if token_data:
        print("✅ Token exchange successful!")

        # Step 5: Test authentication
        print("\n🧪 Step 5: Testing authentication...")
        if await oauth.test_authentication():
            print("\n🎉 Authentication complete! You can now use the MCP server with write operations.")

            print("\n📋 Next steps:")
            print("1. Your MCP server is ready for write operations")
            print("2. You can create changesets and edit OSM data")
            print("3. Try running: python test_comprehensive.py")

        else:
            print("❌ Authentication test failed")
    else:
        print("❌ Token exchange failed")

if __name__ == "__main__":
    asyncio.run(main())