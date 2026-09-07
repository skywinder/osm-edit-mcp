"""Protocol-facing tests for the safe GPX road-edit prompt."""

import pytest
from mcp.types import TextContent

from src.osm_edit_mcp.server import mcp


@pytest.mark.asyncio
async def test_prompts_list_describes_review_gpx_road_edit_arguments():
    prompts = await mcp.list_prompts()

    prompt = next(item for item in prompts if item.name == "review_gpx_road_edit")
    assert prompt.title == "Review a GPX road edit"
    assert prompt.description is not None
    assert "non-writing" in prompt.description
    arguments = [
        (argument.name, argument.required) for argument in prompt.arguments or []
    ]
    assert arguments == [
        ("gpx_path", True),
        ("edit_goal", True),
    ]


@pytest.mark.asyncio
async def test_prompts_get_returns_ordered_workflow_and_exact_confirmation_gate():
    result = await mcp.get_prompt(
        "review_gpx_road_edit",
        {
            "gpx_path": "/imports/survey.gpx",
            "edit_goal": "Review a missing residential road",
        },
    )

    assert len(result.messages) == 1
    message = result.messages[0]
    assert message.role == "user"
    assert isinstance(message.content, TextContent)
    text = message.content.text

    assert 'gpx_path: "/imports/survey.gpx"' in text
    assert 'edit_goal: "Review a missing residential road"' in text
    ordered_steps = [
        "get_edit_capabilities",
        "analyze_gpx_track",
        "create_track_selection",
        "suggest_track_road_candidates",
        "preview_track_road_edit",
    ]
    positions = [text.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    assert "Never silently choose a segment" in text
    assert "explicitly select exactly one segment_id" in text
    assert "exact target_way_ids" in text
    assert "STOP after preview_track_road_edit returns" in text
    assert "complete proposal_digest" in text
    assert "Do not call apply_osm_edit" in text
    assert "or apply_track_road_edit" in text
    assert "user later explicitly requests application" in text
    assert "MCP host separately confirms the same exact proposal_digest" in text
    assert "are not write confirmation" in text


@pytest.mark.asyncio
async def test_prompt_registration_does_not_change_tool_or_resource_counts():
    assert len(await mcp.list_tools()) == 29
    assert len(await mcp.list_resources()) == 0
    assert len(await mcp.list_resource_templates()) == 2
