"""OAuth token loading and identity metadata.

The current storage format remains compatible with the legacy server. Keeping
it behind this module makes a later keyring-only migration local and testable.
"""

import json
import os
from typing import Any, Dict, Optional

from .config import config, logger

def load_oauth_token() -> Optional[Dict[str, Any]]:
    """Load OAuth token from file"""
    try:
        token_file = '.osm_token_dev.json' if config.osm_use_dev_api else '.osm_token_prod.json'
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                token_data: Dict[str, Any] = json.load(f)
            logger.debug(f"Loaded OAuth token from {token_file}")
            return token_data
        return None
    except Exception as e:
        logger.error(f"Failed to load OAuth token: {e}")
        return None

def get_current_user_info() -> Optional[Dict[str, Any]]:
    """Get current authenticated user information"""
    token_data = load_oauth_token()
    if token_data:
        return {
            'user_id': token_data.get('user_id'),
            'username': token_data.get('username'),
            'expires_at': token_data.get('expires_at'),
            'scopes': token_data.get('scope', '').split()
        }
    return None
