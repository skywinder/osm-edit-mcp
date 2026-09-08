"""Release metadata has one canonical version and one packaging definition."""

from importlib.metadata import version
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

from osm_edit_mcp import __version__
from osm_edit_mcp.app import mcp

ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as pyproject:
        return tomllib.load(pyproject)["project"]


def test_distribution_and_runtime_versions_match_pyproject() -> None:
    project = _project_metadata()

    assert project["version"] == "0.2.1"
    assert version(project["name"]) == project["version"]
    assert __version__ == project["version"]


def test_release_metadata_and_entrypoint_are_canonical() -> None:
    project = _project_metadata()

    assert project["authors"] == [{"name": "skywinder"}]
    assert project["scripts"] == {"osm-edit-mcp": "osm_edit_mcp.server:main"}
    assert any(
        dependency.startswith("mcp>=1.29.1") and "<2" in dependency
        for dependency in project["dependencies"]
    )
    assert not (ROOT / "setup.py").exists()
    assert not (ROOT / "requirements.txt").exists()


def test_readme_advertises_the_canonical_pypi_uvx_install() -> None:
    project = _project_metadata()
    package_name = project["name"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert f"https://pypi.org/project/{package_name}/" in readme
    assert f"uvx {package_name}" in readme
    assert '"command": "uvx"' in readme
    assert f'"args": ["{package_name}"]' in readme


def test_runtime_defaults_use_distribution_version(config_factory) -> None:
    config = config_factory()

    assert config.mcp_server_version == __version__
    assert config.default_changeset_created_by == f"osm-edit-mcp/{__version__}"


def test_mcp_initialize_metadata_uses_distribution_version() -> None:
    initialization = mcp._mcp_server.create_initialization_options()

    assert initialization.server_name == "osm-edit-mcp"
    assert initialization.server_version == __version__
