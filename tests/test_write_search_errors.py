"""Failed bounded searches must stop legacy workflows without mutations."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,action",
    [
        ("find_and_update_place", "update"),
        ("delete_place_from_description", "delete"),
    ],
)
async def test_legacy_workflow_preserves_scoped_search_error(
    monkeypatch, tool_name, action
):
    from src.osm_edit_mcp import write_tools

    failure = {
        "success": False,
        "error": "Geographical scope required: supply bbox or lat, lon and radius_meters",
        "message": "Scoped text search failed",
    }
    search = AsyncMock(return_value=failure)
    monkeypatch.setattr(write_tools, "search_osm_elements", search)
    monkeypatch.setattr(
        write_tools,
        "parse_natural_language_request",
        lambda text: {"action": action, "name": "Matenadaran", "business_type": None},
    )
    mutations = []
    for name in (
        "create_changeset",
        "update_osm_node",
        "delete_osm_node",
        "delete_osm_way",
        "delete_osm_relation",
    ):
        mock = AsyncMock(side_effect=AssertionError("mutation must not be attempted"))
        monkeypatch.setattr(write_tools, name, mock)
        mutations.append(mock)

    result = await getattr(write_tools, tool_name)(f"{action} Matenadaran")
    search.assert_awaited_once_with(
        "Matenadaran", bbox=None, lat=None, lon=None, radius_meters=None
    )
    for mutation in mutations:
        mutation.assert_not_called()
    assert not result["success"]
    assert result["error"] == failure["error"]
    assert "search_osm_elements" in result["message"]
    assert "bbox" in result["message"]
    assert "radius_meters" in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,action,mutation",
    [
        ("find_and_update_place", "update", "update_osm_node"),
        ("delete_place_from_description", "delete", "delete_osm_node"),
    ],
)
async def test_legacy_workflow_forwards_scope_and_can_reach_mocked_operation(
    monkeypatch, tool_name, action, mutation
):
    from src.osm_edit_mcp import write_tools

    search = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "elements": [
                    {
                        "id": 17,
                        "type": "node",
                        "tags": {"name": "Fixture"},
                        "location": {"lat": 40.18, "lon": 44.51},
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(write_tools, "search_osm_elements", search)
    monkeypatch.setattr(
        write_tools,
        "parse_natural_language_request",
        lambda _: {
            "action": action,
            "name": "Fixture",
            "business_type": None,
            "features": [],
        },
    )
    call = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(write_tools, mutation, call)
    result = await getattr(write_tools, tool_name)(
        "fixture", changeset_id=123, lat=40.18, lon=44.51, radius_meters=500
    )
    assert result["success"]
    search.assert_awaited_once_with(
        "Fixture", bbox=None, lat=40.18, lon=44.51, radius_meters=500
    )
    assert call.await_count == 1
    assert call.await_args.kwargs["node_id"] == 17
