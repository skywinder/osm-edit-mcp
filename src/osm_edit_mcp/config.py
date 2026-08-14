"""Runtime configuration and logging for the OSM MCP service."""

import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

class OSMConfig(BaseSettings):
    """Comprehensive OSM API configuration with dev/prod switching"""

    # API Configuration
    osm_use_dev_api: bool = Field(default=True, description="Use development API for testing")
    osm_api_base: str = Field(default="https://api.openstreetmap.org/api/0.6", description="Production API base URL")
    osm_dev_api_base: str = Field(default="https://api06.dev.openstreetmap.org/api/0.6", description="Development API base URL")

    # OAuth Configuration - Production
    osm_prod_client_id: str = Field(default="", description="Production OAuth client ID")
    osm_prod_client_secret: str = Field(default="", description="Production OAuth client secret")
    osm_prod_redirect_uri: str = Field(default="https://localhost:8080/callback", description="Production OAuth redirect URI")

    # OAuth Configuration - Development
    osm_dev_client_id: str = Field(default="", description="Development OAuth client ID")
    osm_dev_client_secret: str = Field(default="", description="Development OAuth client secret")
    osm_dev_redirect_uri: str = Field(default="https://localhost:8080/callback", description="Development OAuth redirect URI")

    # Legacy OAuth Configuration (for backward compatibility)
    osm_oauth_client_id: str = Field(default="", alias="osm_client_id")
    osm_oauth_client_secret: str = Field(default="", alias="osm_client_secret")
    osm_oauth_redirect_uri: str = Field(default="http://localhost:8080/callback", alias="osm_redirect_uri")

    # MCP Server Configuration
    mcp_server_name: str = Field(default="osm-edit-mcp")
    mcp_server_version: str = Field(default="0.1.0")

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    debug: bool = Field(default=False)
    development_mode: bool = Field(default=False)

    # Safety and Rate Limiting. Track-edit previews enforce confirmation and the
    # local changeset cap; legacy tools do not yet share a global rate limiter.
    require_user_confirmation: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=60)
    max_changeset_size: int = Field(default=50)

    # GPX road editing. File input is deliberately restricted to one import
    # directory; callers that cannot place files there can pass inline XML.
    osm_track_import_dir: Path = Field(default=Path("tracks"))
    osm_track_max_file_bytes: int = Field(default=16 * 1024 * 1024)
    osm_track_max_points: int = Field(default=100_000)
    osm_track_proposal_ttl_seconds: int = Field(default=30 * 60)

    # Cache Configuration - not yet used by the legacy read tools.
    enable_cache: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=300)

    # Default Changeset Information
    default_changeset_comment: str = Field(default="Edited via OSM Edit MCP Server")
    default_changeset_source: str = Field(default="OSM Edit MCP Server")
    default_changeset_created_by: str = Field(default="osm-edit-mcp/0.1.0")

    # Security Settings
    use_keyring: bool = Field(default=True)

    # Backward compatibility
    osm_api_base_url: str = Field(default="", description="Legacy field for backward compatibility")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from environment

    @property
    def current_api_base_url(self) -> str:
        """Get the current API base URL based on dev/prod setting"""
        if self.osm_api_base_url:  # Backward compatibility
            return self.osm_api_base_url
        return self.osm_dev_api_base if self.osm_use_dev_api else self.osm_api_base

    @property
    def current_client_id(self) -> str:
        """Get the current OAuth client ID based on dev/prod setting"""
        if self.osm_oauth_client_id:  # Backward compatibility
            return self.osm_oauth_client_id
        return self.osm_dev_client_id if self.osm_use_dev_api else self.osm_prod_client_id

    @property
    def current_client_secret(self) -> str:
        """Get the current OAuth client secret based on dev/prod setting"""
        if self.osm_oauth_client_secret:  # Backward compatibility
            return self.osm_oauth_client_secret
        return self.osm_dev_client_secret if self.osm_use_dev_api else self.osm_prod_client_secret

    @property
    def current_redirect_uri(self) -> str:
        """Get the current OAuth redirect URI based on dev/prod setting"""
        if self.osm_oauth_redirect_uri:  # Backward compatibility
            return self.osm_oauth_redirect_uri
        return self.osm_dev_redirect_uri if self.osm_use_dev_api else self.osm_prod_redirect_uri

    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.osm_use_dev_api or self.development_mode or self.debug

config = OSMConfig()

# Every OSM service we talk to (the API, Overpass and Nominatim) requires a
# descriptive User-Agent. Overpass in particular rejects httpx's default with
# "406 Not Acceptable", so all outbound clients must set this.
USER_AGENT = f"osm-edit-mcp/{config.mcp_server_version} (+https://github.com/skywinder/osm-edit-mcp)"

# Configure logging
def setup_logging() -> logging.Logger:
    """Setup structured logging with configurable levels"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
        ]
    )

    # Create logger for this module
    logger = logging.getLogger(__name__)

    # Log configuration info
    logger.info(f"OSM Edit MCP Server v{config.mcp_server_version}")
    logger.info(f"API Mode: {'Development' if config.is_development else 'Production'}")
    logger.info(f"API Base URL: {config.current_api_base_url}")
    logger.info(f"Log Level: {config.log_level}")

    if not config.osm_use_dev_api:
        logger.warning(
            "PRODUCTION MODE: writes go to the live OpenStreetMap database at %s. "
            "Edits are public, permanent and visible to every OSM user. "
            "Set OSM_USE_DEV_API=true to target the sandbox instead.",
            config.osm_api_base,
        )

    return logger

# Initialize logging
logger = setup_logging()
