"""Test configuration management."""
import pytest
from src.osm_edit_mcp.server import OSMConfig


def test_default_config():
    """Test default configuration values."""
    config = OSMConfig()
    assert config.osm_use_dev_api is True
    assert config.osm_dev_api_base == "https://api06.dev.openstreetmap.org/api/0.6"
    assert config.osm_api_base == "https://api.openstreetmap.org/api/0.6"
    assert config.default_changeset_comment == "Edited via OSM Edit MCP Server"
    assert config.require_user_confirmation is True
    assert config.rate_limit_per_minute == 60
    assert config.max_changeset_size == 50


def test_current_api_base_url():
    """Test API URL selection based on dev/prod setting."""
    config = OSMConfig()
    
    # Test development mode
    config.osm_use_dev_api = True
    assert config.current_api_base_url == config.osm_dev_api_base
    
    # Test production mode
    config.osm_use_dev_api = False
    assert config.current_api_base_url == config.osm_api_base


def test_oauth_config_selection():
    """Test OAuth configuration selection based on dev/prod."""
    config = OSMConfig()
    
    # Set test values
    config.osm_dev_client_id = "dev_id"
    config.osm_prod_client_id = "prod_id"
    config.osm_dev_client_secret = "dev_secret"
    config.osm_prod_client_secret = "prod_secret"
    
    # Test development mode
    config.osm_use_dev_api = True
    assert config.current_client_id == "dev_id"
    assert config.current_client_secret == "dev_secret"
    
    # Test production mode
    config.osm_use_dev_api = False
    assert config.current_client_id == "prod_id"
    assert config.current_client_secret == "prod_secret"


def test_is_development_mode():
    """Test development mode detection."""
    config = OSMConfig()
    
    # Test with dev API
    config.osm_use_dev_api = True
    config.development_mode = False
    config.debug = False
    assert config.is_development is True
    
    # Test with development_mode flag
    config.osm_use_dev_api = False
    config.development_mode = True
    config.debug = False
    assert config.is_development is True
    
    # Test with debug flag
    config.osm_use_dev_api = False
    config.development_mode = False
    config.debug = True
    assert config.is_development is True
    
    # Test production mode
    config.osm_use_dev_api = False
    config.development_mode = False
    config.debug = False
    assert config.is_development is False