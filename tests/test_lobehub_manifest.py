"""Keep the owner-declared LobeHub manifest aligned with the MCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from osm_edit_mcp import __version__
from osm_edit_mcp.server import mcp

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "lhm.plugin.json"


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_lobehub_owner_metadata_is_release_metadata() -> None:
    manifest = load_manifest()

    assert manifest["identifier"] == "pk-osm-edit-mcp"
    assert manifest["name"] == "OSM Edit MCP Server"
    assert manifest["version"] == __version__ == "0.2.2"
    assert manifest["author"] == "skywinder"
    assert manifest["authorUrl"] == "https://github.com/skywinder"
    assert manifest["homepage"] == "https://github.com/skywinder/osm-edit-mcp"
    assert "cloudEndpoint" not in manifest
    assert "deploymentOptions" not in manifest


@pytest.mark.asyncio
async def test_lobehub_capabilities_match_the_server() -> None:
    manifest = load_manifest()
    manifest_tools = manifest["tools"]
    manifest_resources = manifest["resources"]
    manifest_prompts = manifest["prompts"]

    assert isinstance(manifest_tools, list)
    assert isinstance(manifest_resources, list)
    assert isinstance(manifest_prompts, list)

    tools = await mcp.list_tools()
    templates = await mcp.list_resource_templates()
    prompts = await mcp.list_prompts()

    assert {tool["name"] for tool in manifest_tools} == {tool.name for tool in tools}
    runtime_tools = {
        tool.name: tool.model_dump(by_alias=True, exclude_none=True) for tool in tools
    }
    for declared_tool in manifest_tools:
        runtime_tool = runtime_tools[declared_tool["name"]]
        assert declared_tool["inputSchema"] == runtime_tool["inputSchema"]
        assert declared_tool["outputSchema"] == runtime_tool["outputSchema"]
        assert declared_tool["annotations"] == runtime_tool["annotations"]
        assert (
            declared_tool["description"].split() == runtime_tool["description"].split()
        )
    assert {resource["uriTemplate"] for resource in manifest_resources} == {
        str(template.uriTemplate) for template in templates
    }
    assert {prompt["name"] for prompt in manifest_prompts} == {
        prompt.name for prompt in prompts
    }
    assert len(manifest_tools) == 31
    assert len(manifest_resources) == 2
    assert len(manifest_prompts) == 1
