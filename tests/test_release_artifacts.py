"""Validate source-archive safety checks used by CI and release jobs."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from scripts.check_release_artifacts import (
    forbidden_payloads,
    validate_source_archive,
)


REQUIRED_SOURCE_FILES = {
    ".env.example",
    "LICENSE",
    "README.md",
    "lhm.plugin.json",
    "pyproject.toml",
    "src/osm_edit_mcp/server.py",
    "uv.lock",
}


def _write_archive(path: Path, names: set[str]) -> None:
    with tarfile.open(path, "w") as archive:
        for name in sorted(names):
            payload = b"release-test\n"
            member = tarfile.TarInfo(f"osm-edit-mcp-0.2.1/{name}")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))


def test_forbidden_payloads_cover_local_and_generated_state() -> None:
    names = {
        ".env",
        ".env.example",
        ".env.production",
        ".claude/settings.local.json",
        "dist/old.whl",
        "private/survey.GPX",
        "private/signing.pem",
        "state/proposals.sqlite3",
        "state/proposals.sqlite3-wal",
    }

    assert forbidden_payloads(names) == [
        ".claude/settings.local.json",
        ".env",
        ".env.production",
        "dist/old.whl",
        "private/signing.pem",
        "private/survey.GPX",
        "state/proposals.sqlite3",
        "state/proposals.sqlite3-wal",
    ]


def test_clean_rooted_source_archive_is_accepted(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar"
    _write_archive(archive, REQUIRED_SOURCE_FILES)

    validate_source_archive(archive)


def test_source_archive_rejects_sqlite_sidecar(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar"
    _write_archive(archive, REQUIRED_SOURCE_FILES | {"state/proposals.sqlite3-wal"})

    with pytest.raises(SystemExit, match="source archive contains forbidden files"):
        validate_source_archive(archive)
