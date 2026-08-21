"""Runtime configuration and logging for the OSM MCP service."""

import logging
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_proposal_db_path() -> Path:
    """Return a per-user data path, never a repository-tracked location."""
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path.home() / ".local" / "share"
    return root / "osm-edit-mcp" / "proposals.sqlite3"


class OSMConfig(BaseSettings):
    """Comprehensive OSM API configuration with dev/prod switching"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    osm_use_dev_api: bool = Field(
        default=True, description="Use development API for testing"
    )
    osm_api_base: str = Field(
        default="https://api.openstreetmap.org/api/0.6",
        description="Production API base URL",
    )
    osm_dev_api_base: str = Field(
        default="https://api06.dev.openstreetmap.org/api/0.6",
        description="Development API base URL",
    )

    # OAuth Configuration - Production
    osm_prod_client_id: str = Field(
        default="", description="Production OAuth client ID"
    )
    osm_prod_client_secret: str = Field(
        default="", description="Production OAuth client secret"
    )
    osm_prod_redirect_uri: str = Field(
        default="https://localhost:8080/callback",
        description="Production OAuth redirect URI",
    )

    # OAuth Configuration - Development
    osm_dev_client_id: str = Field(
        default="", description="Development OAuth client ID"
    )
    osm_dev_client_secret: str = Field(
        default="", description="Development OAuth client secret"
    )
    osm_dev_redirect_uri: str = Field(
        default="https://localhost:8080/callback",
        description="Development OAuth redirect URI",
    )

    # Legacy OAuth Configuration (for backward compatibility)
    osm_oauth_client_id: str = Field(default="", alias="osm_client_id")
    osm_oauth_client_secret: str = Field(default="", alias="osm_client_secret")
    osm_oauth_redirect_uri: str = Field(
        default="http://localhost:8080/callback", alias="osm_redirect_uri"
    )

    # MCP Server Configuration
    mcp_server_name: str = Field(default="osm-edit-mcp")
    mcp_server_version: str = Field(default="0.1.0")

    # Logging Configuration
    log_level: str = Field(
        default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    debug: bool = Field(default=False)
    development_mode: bool = Field(default=False)

    # Safety and rate limiting. Every registered safe write flows through a
    # durable proposal and one atomic osmChange upload.
    require_user_confirmation: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=60)
    max_changeset_size: int = Field(default=50)
    osm_write_profile: Literal["safe", "expert"] = Field(default="safe")
    osm_allow_custom_api_base: bool = Field(default=False)
    osm_require_host_confirmation: bool = Field(default=True)
    osm_proposal_db_path: Path = Field(default_factory=_default_proposal_db_path)

    # GPX road editing. File input is deliberately restricted to one import
    # directory; callers that cannot place files there can pass inline XML.
    osm_track_import_dir: Path = Field(default=Path("tracks"))
    osm_track_max_file_bytes: int = Field(default=10 * 1024 * 1024)
    osm_track_max_points: int = Field(default=100_000)
    osm_track_proposal_ttl_seconds: int = Field(default=30 * 60)
    osm_valhalla_url: str = Field(default="http://127.0.0.1:8002")
    osm_valhalla_timeout_seconds: float = Field(default=30.0)
    osm_permitted_imagery_sources: str = Field(default="")

    # Cache Configuration - not yet used by the legacy read tools.
    enable_cache: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=300)

    # Default Changeset Information
    default_changeset_comment: str = Field(default="Edited via OSM Edit MCP Server")
    default_changeset_source: str = Field(default="OSM Edit MCP Server")
    default_changeset_created_by: str = Field(default="osm-edit-mcp/0.1.0")

    # Security Settings
    use_keyring: bool = Field(default=True)
    allow_plaintext_token_file: bool = Field(default=False)

    # Backward compatibility
    osm_api_base_url: str = Field(
        default="", description="Legacy field for backward compatibility"
    )

    @property
    def current_api_base_url(self) -> str:
        """Get the current API base URL based on dev/prod setting"""
        selected = (
            self.osm_api_base_url
            if self.osm_api_base_url
            else self.osm_dev_api_base if self.osm_use_dev_api else self.osm_api_base
        )
        self.assert_safe_api_target(selected)
        return selected.rstrip("/")

    @property
    def current_web_base_url(self) -> str:
        return (
            "https://api06.dev.openstreetmap.org"
            if self.osm_use_dev_api
            else "https://www.openstreetmap.org"
        )

    @property
    def direct_write_tools_enabled(self) -> bool:
        """Raw writes are available only in an explicitly selected dev profile."""
        return self.osm_write_profile == "expert" and self.osm_use_dev_api

    @property
    def permitted_imagery_sources(self) -> set[str]:
        return {
            source.strip().casefold()
            for source in self.osm_permitted_imagery_sources.split(",")
            if source.strip()
        }

    def assert_safe_api_target(self, value: str) -> None:
        """Prevent OAuth bearer tokens from being sent to an arbitrary host."""
        if self.osm_allow_custom_api_base:
            return
        parsed = urlparse(value)
        allowed = {
            "https://api.openstreetmap.org/api/0.6",
            "https://api06.dev.openstreetmap.org/api/0.6",
        }
        normalized = value.rstrip("/")
        if normalized not in allowed or parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(
                "OSM API target is not allowlisted; set "
                "OSM_ALLOW_CUSTOM_API_BASE=true only for a trusted deployment"
            )

    @property
    def current_client_id(self) -> str:
        """Get the current OAuth client ID based on dev/prod setting"""
        if self.osm_oauth_client_id:  # Backward compatibility
            return self.osm_oauth_client_id
        return (
            self.osm_dev_client_id if self.osm_use_dev_api else self.osm_prod_client_id
        )

    @property
    def current_client_secret(self) -> str:
        """Get the current OAuth client secret based on dev/prod setting"""
        if self.osm_oauth_client_secret:  # Backward compatibility
            return self.osm_oauth_client_secret
        return (
            self.osm_dev_client_secret
            if self.osm_use_dev_api
            else self.osm_prod_client_secret
        )

    @property
    def current_redirect_uri(self) -> str:
        """Get the current OAuth redirect URI based on dev/prod setting"""
        if self.osm_oauth_redirect_uri:  # Backward compatibility
            return self.osm_oauth_redirect_uri
        return (
            self.osm_dev_redirect_uri
            if self.osm_use_dev_api
            else self.osm_prod_redirect_uri
        )

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
        ],
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
