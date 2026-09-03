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

Set OSM_EDIT_MCP_ENV_FILE=/absolute/path/to/.env to load dotenv credentials.
"""

import asyncio
import base64
import getpass
import hashlib
import json
import os
import secrets
import sys
import webbrowser
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import keyring
from dotenv import load_dotenv

from osm_edit_mcp.auth import (
    _parse_identity,
    _parse_permissions,
    has_write_api_permission,
)
from osm_edit_mcp.config import validated_env_file
from osm_edit_mcp.token_store import save_oauth_token

# Dotenv loading is explicit so importing this helper never mutates the process
# from an unrelated working-directory .env.
_configured_env_file = os.environ.get("OSM_EDIT_MCP_ENV_FILE")
if _configured_env_file:
    load_dotenv(validated_env_file(_configured_env_file))


def _trusted_user_id(token_data):
    """Return a locally persisted OSM user id only when it is unambiguous."""
    value = token_data.get("user_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        user_id = value
    elif isinstance(value, str) and value.strip().isdigit():
        user_id = int(value.strip())
    else:
        return None
    return user_id if user_id > 0 else None


def _replacement_account_gate(
    *, has_existing_record, stored_token, live_identity, allow_account_change
):
    """Choose the account constraint before starting a replacement OAuth flow."""
    if allow_account_change:
        return True, None

    if live_identity is not None:
        live_user_id = _trusted_user_id(live_identity)
        if live_user_id is not None:
            return True, live_user_id

    stored_user_id = _trusted_user_id(stored_token)
    if stored_user_id is not None:
        return True, stored_user_id

    if has_existing_record:
        return False, None
    return True, None


def _prompt_for_redirect_url():
    """Read a redirect URL without surfacing a traceback on terminal cancellation."""
    try:
        return getpass.getpass("Redirect URL (hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n❌ Authorization cancelled; the existing token is unchanged")
        return None


class OSMOAuth:
    def __init__(self, use_dev_api=True):
        self.use_dev_api = use_dev_api
        self.state = secrets.token_urlsafe(32)
        self.code_verifier = secrets.token_urlsafe(64)
        self.code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(self.code_verifier.encode("ascii")).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )

        # Get OAuth credentials from environment based on dev/prod setting
        if self.use_dev_api:
            self.client_id = os.getenv("OSM_DEV_CLIENT_ID")
            self.client_secret = os.getenv("OSM_DEV_CLIENT_SECRET")
            self.redirect_uri = (
                os.getenv("OSM_DEV_REDIRECT_URI") or "https://localhost:8080/callback"
            )
        else:
            self.client_id = os.getenv("OSM_PROD_CLIENT_ID")
            self.client_secret = os.getenv("OSM_PROD_CLIENT_SECRET")
            self.redirect_uri = (
                os.getenv("OSM_PROD_REDIRECT_URI") or "https://localhost:8080/callback"
            )

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
        print(f"🔑 Client ID: {'configured' if self.client_id else 'missing'}")
        print(f"🔄 Redirect URI: {self.redirect_uri}")

    def get_authorization_url(self):
        """Generate the authorization URL for OAuth flow."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read_prefs write_api",
            "state": self.state,
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256",
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
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.code_verifier,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_url, data=data, headers={"Accept": "application/json"}
                )

                if response.status_code == 200:
                    token_data = response.json()

                    token_data["expires_at"] = (
                        datetime.now().astimezone()
                        + timedelta(seconds=token_data.get("expires_in", 3600))
                    ).isoformat()
                    return token_data
                else:
                    print(f"❌ Token exchange failed: {response.status_code}")
                    return None

        except Exception as e:
            print(f"❌ Error during token exchange: {type(e).__name__}")
            return None

    async def validate_access_token(self, access_token, expected_user_id=None):
        """Validate a candidate token against live identity and permissions."""
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                details = await client.get(
                    f"{self.api_base}/api/0.6/user/details", headers=headers
                )
                permissions_response = await client.get(
                    f"{self.api_base}/api/0.6/permissions", headers=headers
                )

            if details.status_code != 200:
                print(f"❌ Identity verification failed: HTTP {details.status_code}")
                return None
            if permissions_response.status_code != 200:
                print(
                    "❌ Permission verification failed: "
                    f"HTTP {permissions_response.status_code}"
                )
                return None

            identity = _parse_identity(details.text)
            permissions = _parse_permissions(permissions_response.text)
            if expected_user_id is not None and identity["user_id"] != expected_user_id:
                print("❌ OAuth account changed; refusing to replace the existing token")
                return None
            if not has_write_api_permission(permissions):
                print("❌ OAuth token does not grant write_api")
                return None

            print("✅ Authentication and write_api permission verified")
            print(
                f"👤 Logged in as: {identity['username']} "
                f"(ID: {identity['user_id']})"
            )
            return {**identity, "permissions": sorted(permissions)}

        except Exception as e:
            print(f"❌ Error testing authentication: {type(e).__name__}")
            return None

    def load_existing_token_record(self):
        """Load keyring token metadata while retaining conservative record state."""
        keyring_service = f"osm-edit-mcp-{'dev' if self.use_dev_api else 'prod'}"
        token_data = {}
        has_existing_record = False

        try:
            serialized = keyring.get_password(keyring_service, "token_json")
            if serialized is not None:
                has_existing_record = True
                try:
                    parsed = json.loads(serialized)
                except (json.JSONDecodeError, TypeError):
                    print("⚠️  Existing token metadata is unreadable")
                else:
                    if isinstance(parsed, dict):
                        token_data = parsed
                    else:
                        print("⚠️  Existing token metadata has an invalid format")
        except Exception as e:
            print(f"❌ Could not read the existing token: {type(e).__name__}")
            # A read failure cannot prove that the entry is absent. Treat it as
            # existing so account replacement requires explicit authorization.
            has_existing_record = True

        if not token_data.get("access_token"):
            try:
                legacy_access_token = keyring.get_password(
                    keyring_service, "access_token"
                )
                if legacy_access_token:
                    has_existing_record = True
                    token_data["access_token"] = legacy_access_token
            except Exception as e:
                print(f"❌ Could not read the legacy token: {type(e).__name__}")
                has_existing_record = True

        return token_data, has_existing_record

    async def test_authentication(self, token_data=None):
        """Validate the currently stored token without changing keyring state."""
        if token_data is None:
            token_data, _ = self.load_existing_token_record()
        access_token = token_data.get("access_token")
        if not access_token:
            print("❌ No access token found. Please authenticate first.")
            return None
        return await self.validate_access_token(access_token)

    async def validate_and_save_token(self, token_data, expected_user_id=None):
        """Persist a replacement only after live account and scope validation."""
        access_token = token_data.get("access_token")
        if not access_token:
            print("❌ Token response did not contain an access token")
            return None
        identity = await self.validate_access_token(access_token, expected_user_id)
        if identity is None:
            print("❌ Candidate token was not saved; the existing token is unchanged")
            return None
        token_data.update(identity)
        try:
            save_oauth_token(token_data, use_dev_api=self.use_dev_api)
        except Exception as e:
            print(f"❌ Could not save the validated token: {type(e).__name__}")
            return None
        print("✅ Validated token saved to the OS keyring")
        return identity


async def main():
    """Main OAuth authentication flow."""
    print("🚀 OSM Edit MCP Server - OAuth Authentication")
    print("=" * 50)

    args = set(sys.argv[1:])
    valid_args = {
        "--prod",
        "--production",
        "--dev",
        "--development",
        "--reauthorize",
        "--allow-account-change",
        "--no-browser",
        "-h",
        "--help",
    }
    unknown_args = args - valid_args
    if unknown_args:
        print(f"Unknown argument: {sorted(unknown_args)[0]}")
        print("Use --help for usage information")
        return

    if "-h" in args or "--help" in args:
        print("Usage:")
        print("  python oauth_auth.py              # Development API (default)")
        print("  python oauth_auth.py --dev        # Development API (explicit)")
        print("  python oauth_auth.py --prod       # Production API")
        print("  python oauth_auth.py --reauthorize  # Replace a token safely")
        print(
            "  python oauth_auth.py --reauthorize --allow-account-change"
            "  # Intentionally change OSM account"
        )
        print("  python oauth_auth.py --no-browser   # Print URL without opening it")
        return

    prod_requested = bool(args & {"--prod", "--production"})
    dev_requested = bool(args & {"--dev", "--development"})
    if prod_requested and dev_requested:
        print("Choose either --prod or --dev, not both")
        return

    force_reauthorize = "--reauthorize" in args
    allow_account_change = "--allow-account-change" in args
    open_browser = "--no-browser" not in args
    if allow_account_change and not force_reauthorize:
        print("--allow-account-change requires --reauthorize")
        return

    # Determine which API to use
    use_dev_api = True  # Default to dev for safety

    # Check command-line arguments
    if prod_requested:
        use_dev_api = False
        print("⚠️  WARNING: Using PRODUCTION API - changes affect real OSM data!")
    elif dev_requested:
        use_dev_api = True
    # Check environment variable as fallback
    elif os.getenv("OSM_USE_PROD_API", "").lower() in ["true", "1", "yes"]:
        use_dev_api = False
        print("⚠️  WARNING: Using PRODUCTION API (from OSM_USE_PROD_API env var)")

    # Initialize OAuth
    oauth = OSMOAuth(use_dev_api=use_dev_api)

    if not oauth.client_id or not oauth.client_secret:
        print("❌ Missing OAuth credentials!")
        if use_dev_api:
            print(
                "Please set OSM_DEV_CLIENT_ID and OSM_DEV_CLIENT_SECRET in your .env file"
            )
        else:
            print(
                "Please set OSM_PROD_CLIENT_ID and OSM_PROD_CLIENT_SECRET in your .env file"
            )
        return

    # Test if we already have valid authentication
    print("\n📋 Testing existing authentication...")
    stored_token, has_existing_record = oauth.load_existing_token_record()
    existing_identity = await oauth.test_authentication(stored_token)
    if not force_reauthorize and existing_identity:
        print("🎉 You're already authenticated! Ready to use the MCP server.")
        return
    if force_reauthorize:
        print("♻️  Reauthorization requested; preserving the existing token until exchange")

    replacement_allowed, expected_user_id = _replacement_account_gate(
        has_existing_record=has_existing_record,
        stored_token=stored_token,
        live_identity=existing_identity,
        allow_account_change=allow_account_change,
    )
    if not replacement_allowed:
        print(
            "❌ The existing token cannot be tied to a trusted OSM account; "
            "it will not be replaced"
        )
        print(
            "To intentionally authorize another account, rerun with "
            "--reauthorize --allow-account-change"
        )
        return

    print("\n🔐 Starting OAuth authentication flow...")

    # Step 1: Get authorization URL
    auth_url = oauth.get_authorization_url()
    print(f"\n📝 Step 1: Please visit this URL to authorize the application:")
    print(f"🔗 {auth_url}")

    # Try to open URL in browser
    if open_browser:
        try:
            webbrowser.open(auth_url)
            print("🌐 Opening browser automatically...")
        except Exception:
            print(
                "⚠️  Could not open browser automatically. "
                "Please copy and paste the URL above."
            )

    print(
        "\n📋 Step 2: After authorizing, you'll be redirected to a URL that starts with:"
    )
    print(f"   {oauth.redirect_uri}?code=...")

    # Get authorization code from user
    print("\n📝 Step 3: Please paste the full redirect URL here:")
    redirect_url = _prompt_for_redirect_url()
    if redirect_url is None:
        return

    # Parse authorization code
    try:
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)

        if "code" not in query_params:
            print("❌ No authorization code found in URL")
            return

        returned_state = query_params.get("state", [None])[0]
        if not returned_state or not secrets.compare_digest(
            returned_state, oauth.state
        ):
            print("❌ OAuth state mismatch; refusing the authorization response")
            return

        authorization_code = query_params["code"][0]
        print("✅ Found authorization code")

    except Exception as e:
        print(f"❌ Error parsing redirect URL: {e}")
        return

    # Step 4: Exchange code for token
    print("\n🔄 Step 4: Exchanging authorization code for access token...")
    token_data = await oauth.exchange_code_for_token(authorization_code)

    if token_data:
        print("✅ Token exchange successful!")

        # Step 5: Validate the candidate before replacing a working token.
        print("\n🧪 Step 5: Validating identity and write_api permission...")
        if await oauth.validate_and_save_token(token_data, expected_user_id):
            print(
                "\n🎉 Authentication complete. The server can now prepare "
                "identity-bound edit proposals."
            )

            print("\n📋 Next steps:")
            print("1. Verify get_edit_capabilities reports the intended account")
            print("2. Prepare and review a preview without writing to OSM")
            print("3. Apply only after exact digest and MCP host confirmation")

        else:
            print("❌ Authentication validation failed")
    else:
        print("❌ Token exchange failed")


if __name__ == "__main__":
    asyncio.run(main())
