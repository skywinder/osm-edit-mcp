#!/usr/bin/env python3
"""Validate tag/version alignment and the contents of release artifacts."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_BASENAMES = {
    ".env",
    "requirements.txt",
    "settings.local.json",
    "setup.py",
}
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
FORBIDDEN_SUFFIXES = {".cer", ".crt", ".gpx", ".key", ".p12", ".pem", ".pfx"}
SQLITE_TRANSIENT_SUFFIXES = {"-journal", "-shm", "-wal"}
EXPECTED_WHEEL_FILES = {
    "osm_edit_mcp/_version.py",
    "osm_edit_mcp/config.py",
    "osm_edit_mcp/server.py",
    "osm_edit_mcp/track_tools.py",
}


def project_metadata() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as pyproject:
        return tomllib.load(pyproject)["project"]


def validate_tag(tag: str, project: dict[str, Any]) -> None:
    expected = f"v{project['version']}"
    if tag != expected:
        raise SystemExit(f"release tag {tag!r} must exactly match {expected!r}")


def only_artifact(dist: Path, pattern: str, label: str) -> Path:
    matches = sorted(dist.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one {label} in {dist}, found {len(matches)}"
        )
    return matches[0]


def parse_metadata(payload: bytes) -> Any:
    return BytesParser(policy=policy.default).parsebytes(payload)


def forbidden_payloads(names: set[str]) -> list[str]:
    """Return local-only or stale paths that must never ship."""
    forbidden: list[str] = []
    for name in names:
        path = PurePosixPath(name)
        parts = tuple(part.casefold() for part in path.parts)
        basename = path.name.casefold()
        suffix = path.suffix.casefold()
        is_dotenv = basename == ".env" or (
            basename.startswith(".env.") and basename != ".env.example"
        )
        is_sqlite_state = suffix in DATABASE_SUFFIXES or any(
            basename.endswith(f"{database_suffix}{transient_suffix}")
            for database_suffix in DATABASE_SUFFIXES
            for transient_suffix in SQLITE_TRANSIENT_SUFFIXES
        )
        if (
            basename in FORBIDDEN_BASENAMES
            or is_dotenv
            or "dist" in parts
            or suffix in FORBIDDEN_SUFFIXES
            or is_sqlite_state
        ):
            forbidden.append(name)
    return sorted(forbidden)


def relative_archive_names(names: set[str]) -> set[str]:
    """Strip one conventional archive root while retaining flat archives."""
    populated = {name.rstrip("/") for name in names if name.rstrip("/")}
    roots = {name.split("/", 1)[0] for name in populated}
    if len(roots) != 1:
        return populated
    root = roots.pop()
    return {
        name.removeprefix(f"{root}/") for name in populated if name != root
    }


def validate_wheel(wheel: Path, project: dict[str, Any]) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_paths = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        entrypoint_paths = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(metadata_paths) != 1 or len(entrypoint_paths) != 1:
            raise SystemExit("wheel must contain one METADATA and one entry_points.txt")

        metadata = parse_metadata(archive.read(metadata_paths[0]))
        if metadata["Name"] != project["name"]:
            raise SystemExit(f"wheel Name is {metadata['Name']!r}")
        if metadata["Version"] != project["version"]:
            raise SystemExit(f"wheel Version is {metadata['Version']!r}")

        missing = EXPECTED_WHEEL_FILES - names
        if missing:
            raise SystemExit(f"wheel is missing package files: {sorted(missing)}")
        forbidden = forbidden_payloads(names)
        if forbidden:
            raise SystemExit(f"wheel contains forbidden files: {forbidden}")

        entrypoints = archive.read(entrypoint_paths[0]).decode("utf-8")
        expected = "osm-edit-mcp = osm_edit_mcp.server:main"
        if expected not in entrypoints:
            raise SystemExit(f"wheel is missing console entry point {expected!r}")


def validate_sdist(sdist: Path, project: dict[str, Any]) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
        roots = {name.split("/", 1)[0] for name in names if name}
        if len(roots) != 1:
            raise SystemExit(f"sdist must contain one root directory, found {roots}")
        root = roots.pop()

        metadata_member = archive.extractfile(f"{root}/PKG-INFO")
        if metadata_member is None:
            raise SystemExit("sdist is missing PKG-INFO")
        metadata = parse_metadata(metadata_member.read())
        if metadata["Name"] != project["name"]:
            raise SystemExit(f"sdist Name is {metadata['Name']!r}")
        if metadata["Version"] != project["version"]:
            raise SystemExit(f"sdist Version is {metadata['Version']!r}")

        relative_names = {
            name.removeprefix(f"{root}/") for name in names if name != root
        }
        forbidden = forbidden_payloads(relative_names)
        if forbidden:
            raise SystemExit(f"sdist contains forbidden files: {forbidden}")
        if "src/osm_edit_mcp/server.py" not in relative_names:
            raise SystemExit("sdist is missing src/osm_edit_mcp/server.py")
        if "lhm.plugin.json" not in relative_names:
            raise SystemExit("sdist is missing lhm.plugin.json")
        for test_helper in (
            "oauth_auth.py",
            "scripts/security_audit.py",
            "web_server.py",
        ):
            if test_helper not in relative_names:
                raise SystemExit(f"sdist is missing test helper {test_helper}")


def validate_source_archive(source_archive: Path) -> None:
    """Validate the exact public source tree produced by ``git archive``."""
    with tarfile.open(source_archive, "r:*") as archive:
        relative_names = relative_archive_names(set(archive.getnames()))

    forbidden = forbidden_payloads(relative_names)
    if forbidden:
        raise SystemExit(f"source archive contains forbidden files: {forbidden}")

    required = {
        ".env.example",
        "LICENSE",
        "README.md",
        "lhm.plugin.json",
        "pyproject.toml",
        "src/osm_edit_mcp/server.py",
        "uv.lock",
    }
    missing = required - relative_names
    if missing:
        raise SystemExit(f"source archive is missing release files: {sorted(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dist", type=Path, help="directory containing wheel and sdist"
    )
    parser.add_argument(
        "--tag", help="release tag, which must equal v<project.version>"
    )
    parser.add_argument(
        "--archive", type=Path, help="tar archive produced from the public Git tree"
    )
    args = parser.parse_args()

    if args.dist is None and args.tag is None and args.archive is None:
        parser.error("at least one of --dist, --tag, or --archive is required")

    project = project_metadata()
    if args.tag is not None:
        validate_tag(args.tag, project)
    if args.dist is not None:
        validate_wheel(only_artifact(args.dist, "*.whl", "wheel"), project)
        validate_sdist(only_artifact(args.dist, "*.tar.gz", "sdist"), project)
    if args.archive is not None:
        validate_source_archive(args.archive)

    checks = [
        name
        for name, value in (
            ("tag", args.tag),
            ("artifacts", args.dist),
            ("source archive", args.archive),
        )
        if value
    ]
    print(f"release {' and '.join(checks)} verified for v{project['version']}")


if __name__ == "__main__":
    main()
