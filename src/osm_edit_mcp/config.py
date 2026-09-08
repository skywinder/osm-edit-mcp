"""Runtime configuration and logging for the OSM MCP service."""

import logging
import os
import stat
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._version import __version__

PRODUCTION_API_BASE_URL = "https://api.openstreetmap.org/api/0.6"
DEVELOPMENT_API_BASE_URL = "https://api06.dev.openstreetmap.org/api/0.6"


def validated_env_file(value: str | None) -> Path | None:
    """Return an explicit private dotenv path or fail before reading it."""
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("OSM_EDIT_MCP_ENV_FILE must not be a symbolic link")
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ValueError("OSM_EDIT_MCP_ENV_FILE does not exist") from exc
    if not path.is_file():
        raise ValueError("OSM_EDIT_MCP_ENV_FILE must be a regular file")
    if os.name == "posix" and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PermissionError("OSM_EDIT_MCP_ENV_FILE must have permissions 0600")
    return path


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
        # Never consume an unrelated .env from the MCP host's working
        # directory. Operators may opt in with OSM_EDIT_MCP_ENV_FILE.
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    osm_use_dev_api: bool = Field(
        default=True, description="Use development API for testing"
    )
    osm_api_base: str = Field(
        default=PRODUCTION_API_BASE_URL,
        description="Production API base URL",
    )
    osm_dev_api_base: str = Field(
        default=DEVELOPMENT_API_BASE_URL,
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
    mcp_server_version: str = Field(default=__version__)
    osm_tool_profile: Literal["full", "discovery"] = "full"
    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    osm_nominatim_url: str = "https://nominatim.openstreetmap.org"

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
    default_changeset_created_by: str = Field(default=f"osm-edit-mcp/{__version__}")

    # Security Settings
    use_keyring: bool = Field(default=True)
    allow_plaintext_token_file: bool = Field(default=False)

    # Backward compatibility
    osm_api_base_url: str = Field(
        default="", description="Legacy field for backward compatibility"
    )

    @model_validator(mode="after")
    def validate_api_target_mode(self) -> "OSMConfig":
        """Reject a known dev/production target that contradicts its mode."""
        self._validated_api_base_url()
        return self

    def _selected_api_base_url(self) -> str:
        return (
            self.osm_api_base_url
            if self.osm_api_base_url
            else self.osm_dev_api_base if self.osm_use_dev_api else self.osm_api_base
        )

    @staticmethod
    def _classify_api_target(
        value: str,
    ) -> Literal["development", "production", "custom"]:
        normalized = value.rstrip("/")
        if normalized == DEVELOPMENT_API_BASE_URL:
            return "development"
        if normalized == PRODUCTION_API_BASE_URL:
            return "production"
        return "custom"

    def _validated_api_base_url(self) -> str:
        selected = self._selected_api_base_url()
        self.assert_safe_api_target(selected)
        normalized = selected.rstrip("/")
        environment = self._classify_api_target(normalized)
        if environment == "development" and not self.osm_use_dev_api:
            raise ValueError(
                "OSM API target is the development server but "
                "OSM_USE_DEV_API is false"
            )
        if environment == "production" and self.osm_use_dev_api:
            raise ValueError(
                "OSM API target is the production server but OSM_USE_DEV_API is true"
            )
        return normalized

    @property
    def current_api_base_url(self) -> str:
        """Return the normalized, allowlisted and mode-consistent API target."""
        return self._validated_api_base_url()

    @property
    def api_environment(self) -> Literal["development", "production", "custom"]:
        """Classify the actual normalized target, never only a mode boolean."""
        return self._classify_api_target(self.current_api_base_url)

    @property
    def is_development_api(self) -> bool:
        """Return true only for the official OSM development endpoint."""
        return self.api_environment == "development"

    @property
    def current_web_base_url(self) -> str:
        if self.api_environment == "development":
            return "https://api06.dev.openstreetmap.org"
        if self.api_environment == "production":
            return "https://www.openstreetmap.org"
        parsed = urlparse(self.current_api_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def direct_write_tools_enabled(self) -> bool:
        """Raw writes require expert mode and the actual official dev endpoint."""
        return self.osm_write_profile == "expert" and self.is_development_api

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
            PRODUCTION_API_BASE_URL,
            DEVELOPMENT_API_BASE_URL,
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
        environment_client_id = (
            self.osm_dev_client_id if self.osm_use_dev_api else self.osm_prod_client_id
        )
        return environment_client_id or self.osm_oauth_client_id

    @property
    def current_client_secret(self) -> str:
        """Get the current OAuth client secret based on dev/prod setting"""
        environment_client_secret = (
            self.osm_dev_client_secret
            if self.osm_use_dev_api
            else self.osm_prod_client_secret
        )
        return environment_client_secret or self.osm_oauth_client_secret

    @property
    def current_redirect_uri(self) -> str:
        """Get the current OAuth redirect URI based on dev/prod setting"""
        environment_client_id = (
            self.osm_dev_client_id if self.osm_use_dev_api else self.osm_prod_client_id
        )
        environment_client_secret = (
            self.osm_dev_client_secret
            if self.osm_use_dev_api
            else self.osm_prod_client_secret
        )
        if not environment_client_id and not environment_client_secret:
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


_configured_env_file = os.environ.get("OSM_EDIT_MCP_ENV_FILE")
config = OSMConfig(  # type: ignore[call-arg]
    _env_file=validated_env_file(_configured_env_file)
)

# Every OSM service we talk to (the API, Overpass and Nominatim) requires a
# descriptive User-Agent. Overpass in particular rejects httpx's default with
# "406 Not Acceptable", so all outbound clients must set this.
USER_AGENT = f"osm-edit-mcp/{config.mcp_server_version} (+https://github.com/skywinder/osm-edit-mcp)"
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
        # FastMCP configures logging while app.py is imported. Replace that
        # early handler so LOG_LEVEL also controls SDK request logs.
        force=True,
    )

    # Log configuration info
    logger.info(f"OSM Edit MCP Server v{config.mcp_server_version}")
    logger.info("API environment: %s", config.api_environment)
    logger.info(f"API Base URL: {config.current_api_base_url}")
    logger.info(f"Log Level: {config.log_level}")

    if not config.is_development_api:
        logger.warning(
            "NON-DEVELOPMENT API TARGET: %s. Production OSM edits are public "
            "and permanent; custom targets receive the same fail-closed write "
            "gates.",
            config.current_api_base_url,
        )

    return logger
