"""The LobeHub metadata bridge is derived, read-only, and schema-sensitive."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_lobehub_manifest as audit


def fixture_manifest():
    return {
        "identifier": "pk-osm-edit-mcp",
        "version": "0.2.1",
        "tools": [{"name": "inspect", "inputSchema": {"type": "object"}}],
        "resources": [{"name": "preview", "uriTemplate": "ui://preview/{id}"}],
        "prompts": [
            {"name": "review", "arguments": [{"name": "goal", "required": True}]}
        ],
    }


def test_metadata_bridge_is_derived_from_pyproject():
    with (audit.ROOT / "pyproject.toml").open("rb") as handle:
        project = audit.tomllib.load(handle)["project"]
    bridge = audit.package_metadata(project)
    assert bridge["description"] == project["description"]
    assert bridge["version"] == project["version"]
    assert bridge["repository"] == project["urls"]["Repository"]
    assert bridge["author"] == {"name": "skywinder"}
    assert not (audit.ROOT / "package.json").exists()


def test_verification_accepts_generated_identifier_but_preserves_owner_id():
    declared = fixture_manifest()
    discovered = deepcopy(declared)
    discovered["identifier"] = "skywinder-osm-edit-mcp"
    assert audit.verify_manifest(declared, discovered, "0.2.1") == {
        "tools": 1,
        "resources": 1,
        "prompts": 1,
    }
    assert declared["identifier"] == "pk-osm-edit-mcp"


@pytest.mark.parametrize("capability", audit.CAPABILITIES)
def test_verification_rejects_schema_drift_with_unchanged_counts(capability):
    declared = fixture_manifest()
    discovered = deepcopy(declared)
    discovered[capability][0]["description"] = "Unexpected replacement"
    with pytest.raises(ValueError, match=f"Published {capability} differ"):
        audit.verify_manifest(declared, discovered, "0.2.1")


@pytest.mark.parametrize("capability", audit.CAPABILITIES)
def test_verification_rejects_missing_capabilities(capability):
    declared = fixture_manifest()
    discovered = deepcopy(declared)
    discovered[capability] = []
    with pytest.raises(ValueError, match=f"Published {capability} differ"):
        audit.verify_manifest(declared, discovered, "0.2.1")


def test_verification_rejects_version_and_owner_identifier_drift():
    declared = fixture_manifest()
    with pytest.raises(ValueError, match="versions differ"):
        audit.verify_manifest(declared, declared, "0.2.2")
    declared["identifier"] = "skywinder-osm-edit-mcp"
    with pytest.raises(ValueError, match="Owner identifier"):
        audit.verify_manifest(declared, declared, "0.2.1")


def test_description_formatting_does_not_change_schema():
    declared = fixture_manifest()
    discovered = deepcopy(declared)
    declared["tools"][0]["description"] = "Inspect\n  one object"
    discovered["tools"][0]["description"] = "Inspect one object"
    audit.verify_manifest(declared, discovered, "0.2.1")


def test_cli_uses_temporary_metadata_and_never_publishes(monkeypatch, tmp_path):
    project_source = (audit.ROOT / "pyproject.toml").read_text(encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(project_source, encoding="utf-8")
    declared = fixture_manifest()
    manifest_path = tmp_path / "lhm.plugin.json"
    manifest_path.write_text(json.dumps(declared), encoding="utf-8")
    before = manifest_path.read_bytes()
    monkeypatch.setenv("OSM_ACCESS_TOKEN", "test-token-must-not-be-forwarded")
    invocations = []

    def fake_run(command, **kwargs):
        directory = Path(kwargs["cwd"])
        invocations.append(directory)
        assert command[3:5] == ["plugin", "init"]
        assert "publish" not in command and "update" not in command
        assert "OSM_ACCESS_TOKEN" not in kwargs["env"]
        assert kwargs["check"] is True
        assert directory != tmp_path
        bridge = json.loads((directory / "package.json").read_text())
        assert bridge["description"]
        (directory / "lhm.plugin.json").write_text(json.dumps(declared))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    audit.check_published_package(tmp_path)
    assert len(invocations) == 1
    assert not invocations[0].exists()
    assert manifest_path.read_bytes() == before
    assert not (tmp_path / "package.json").exists()
