#!/usr/bin/env python3
"""Check the owner manifest against a released package using LobeHub's CLI.

This is local introspection only: no login, claim, publish, or update is run.
The temporary package.json bridges the CLI's Node-only metadata discovery;
pyproject.toml remains the sole package metadata source.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
MARKET_CLI = "@lobehub/market-cli@0.0.41"
CAPABILITIES = ("tools", "resources", "prompts")


def package_metadata(project: dict[str, Any]) -> dict[str, Any]:
    """Derive only public discovery metadata; never read dotenv or credentials."""
    return {
        "name": project["name"],
        "version": project["version"],
        "description": project["description"],
        "homepage": project["urls"]["Homepage"],
        "repository": project["urls"]["Repository"],
        "author": {"name": project["authors"][0]["name"]},
        "keywords": project.get("keywords", []),
    }


def normalized(value: Any) -> Any:
    """Ignore formatting in descriptions, but retain schemas and safety hints."""
    if isinstance(value, dict):
        return {
            key: (
                " ".join(item.split())
                if key == "description" and isinstance(item, str)
                else normalized(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def serialized_capability(value: Any) -> str:
    return json.dumps(normalized(value), sort_keys=True)


def verify_manifest(
    declared: dict[str, Any], discovered: dict[str, Any], version: str
) -> dict[str, int]:
    """Compare all capability definitions, not just their names or counts."""
    if declared.get("identifier") != "pk-osm-edit-mcp":
        raise ValueError("Owner identifier must remain pk-osm-edit-mcp")
    if declared.get("version") != version or discovered.get("version") != version:
        raise ValueError("Manifest, published server, and package versions differ")
    counts = {}
    for capability in CAPABILITIES:
        expected = declared.get(capability)
        actual = discovered.get(capability)
        if not isinstance(expected, list) or not isinstance(actual, list):
            raise ValueError(f"{capability} must be arrays")
        if not expected:
            raise ValueError(f"{capability} must not be empty")
        # Capability-list ordering is not significant; nested schema arrays are.
        if sorted(map(serialized_capability, expected)) != sorted(
            map(serialized_capability, actual)
        ):
            raise ValueError(f"Published {capability} differ from the owner manifest")
        counts[capability] = len(actual)
    return counts


def check_published_package(root: Path = ROOT) -> dict[str, int]:
    with (root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    declared = json.loads((root / "lhm.plugin.json").read_text(encoding="utf-8"))
    command = shlex.join(
        [
            "uvx",
            "--isolated",
            "--from",
            f"{project['name']}=={project['version']}",
            project["name"],
        ]
    )
    # Do not pass OAuth, dotenv, or OSM environment variables to the CLI.
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")
        if key in os.environ
    }
    with tempfile.TemporaryDirectory(prefix="osm-lobehub-manifest-") as directory:
        temporary = Path(directory)
        (temporary / "package.json").write_text(
            json.dumps(package_metadata(project), indent=2) + "\n", encoding="utf-8"
        )
        subprocess.run(
            [
                "npx",
                "-y",
                MARKET_CLI,
                "plugin",
                "init",
                "--stdio",
                command,
                "--dir",
                str(temporary),
            ],
            cwd=temporary,
            env=environment,
            check=True,
            timeout=120,
        )
        discovered = json.loads(
            (temporary / "lhm.plugin.json").read_text(encoding="utf-8")
        )
    # The CLI infers skywinder-osm-edit-mcp from the repository URL. That draft
    # must never replace or be published over our existing pk-osm-edit-mcp ID.
    return verify_manifest(declared, discovered, project["version"])


def main() -> None:
    try:
        counts = check_published_package()
    except (ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"LobeHub manifest verification failed: {exc}") from exc
    print(f"LobeHub manifest verified for pk-osm-edit-mcp: {json.dumps(counts)}")
    print("No marketplace changes made; checked-in manifest was not overwritten.")


if __name__ == "__main__":
    main()
