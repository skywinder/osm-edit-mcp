"""Runtime access to the version declared by the installed distribution."""

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION_NAME = "osm-edit-mcp"


def get_version() -> str:
    """Return installed package metadata without duplicating the release version."""
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0.0.0+uninstalled"


__version__ = get_version()

__all__ = ["DISTRIBUTION_NAME", "__version__", "get_version"]
