#!/usr/bin/env python3
"""Start an installed console script and verify its MCP stdio surface."""

from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "get_osm_node",
    "get_osm_way",
    "get_osm_relation",
    "get_osm_elements_in_area",
    "get_changeset",
    "get_server_info",
    "check_authentication",
    "search_nearby_places",
    "find_nearby_amenities",
    "get_changeset_history",
    "resolve_location",
    "get_place_details",
    "get_place_info",
    "search_osm_elements",
    "parse_natural_language_osm_request",
    "validate_osm_data",
    "validate_coordinates",
    "export_osm_data",
    "get_osm_statistics",
    "smart_geocode",
    "analyze_gpx_track",
    "create_track_selection",
    "match_track_selection",
    "suggest_track_road_candidates",
    "preview_track_road_edit",
    "apply_osm_edit",
    "apply_track_road_edit",
    "get_edit_capabilities",
    "inspect_map_context",
    "list_edit_proposals",
    "verify_osm_edit",
}
EXPECTED_RESOURCE_TEMPLATES = {
    "ui://osm-edit/proposal/{proposal_id}",
    "ui://osm-edit/track-selection/{selection_id}",
}
EXPECTED_PROMPTS = {"review_gpx_road_edit"}
SYNTHETIC_GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Release smoke survey</name><trkseg>
    <trkpt lat="40.1810" lon="44.5130"/>
    <trkpt lat="40.1811" lon="44.5131"/>
    <trkpt lat="40.1812" lon="44.5132"/>
  </trkseg></trk>
</gpx>
"""


def successful_tool_payload(result: object, tool_name: str) -> dict[str, object]:
    """Return a FastMCP dict result and fail loudly on protocol/tool errors."""
    if getattr(result, "isError", False):
        raise SystemExit(f"{tool_name} returned an MCP error")
    structured = getattr(result, "structuredContent", None)
    if not isinstance(structured, dict):
        raise SystemExit(f"{tool_name} did not return structured content")
    payload = structured.get("result", structured)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise SystemExit(f"{tool_name} did not return a successful result: {payload!r}")
    return payload


async def smoke_test(command: str, *, live_osm_read: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="osm-edit-mcp-smoke-") as temp_dir:
        temp = Path(temp_dir)
        child_env = {
            "LOG_LEVEL": "ERROR",
            "OSM_PROPOSAL_DB_PATH": str(temp / "proposals.sqlite3"),
            "PATH": os.environ.get("PATH", ""),
            "USE_KEYRING": "false",
        }
        if live_osm_read:
            child_env["OSM_USE_DEV_API"] = "false"
        params = StdioServerParameters(command=command, args=[], env=child_env)

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                templates = await session.list_resource_templates()
                prompts = await session.list_prompts()
                prompt = await session.get_prompt(
                    "review_gpx_road_edit",
                    arguments={
                        "gpx_path": "/private/survey.gpx",
                        "edit_goal": "Review one surveyed road segment",
                    },
                )
                analysis_result = await session.call_tool(
                    "analyze_gpx_track", {"gpx_xml": SYNTHETIC_GPX}
                )
                analysis = successful_tool_payload(analysis_result, "analyze_gpx_track")
                analysis_data = analysis.get("data")
                if not isinstance(analysis_data, dict):
                    raise SystemExit("analyze_gpx_track returned no data")
                selection_result = await session.call_tool(
                    "create_track_selection",
                    {
                        "track_id": analysis_data["track_id"],
                        "segment_id": "trk-0-seg-0",
                        "start_point_index": 0,
                        "end_point_index": 2,
                    },
                )
                selection = successful_tool_payload(
                    selection_result, "create_track_selection"
                )
                selection_data = selection.get("data")
                if not isinstance(selection_data, dict):
                    raise SystemExit("create_track_selection returned no data")
                preview_uri = selection_data.get("preview_uri")
                if not isinstance(preview_uri, str):
                    raise SystemExit("track selection did not return preview_uri")
                preview = await session.read_resource(preview_uri)
                # Check the actual installed artifact, not just source imports (#11).
                parser_cases = [
                    ("a public footpath", {}),
                    ("a car park", {"amenity": "parking"}),
                    (
                        "a cafe that is not wheelchair accessible",
                        {
                            "amenity": "cafe",
                            "wheelchair": "no",
                        },
                    ),
                ]
                for text, expected_tags in parser_cases:
                    parsed = successful_tool_payload(
                        await session.call_tool(
                            "parse_natural_language_osm_request", {"request": text}
                        ),
                        "parse_natural_language_osm_request",
                    )
                    if parsed["data"]["suggested_tags"] != expected_tags:
                        raise SystemExit(
                            "installed parser failed word/negation regression"
                        )
                if live_osm_read:
                    live_result = await session.call_tool(
                        "get_osm_node", {"node_id": 1}
                    )
                    successful_tool_payload(live_result, "get_osm_node")

        tool_names = {tool.name for tool in tools.tools}
        expected = EXPECTED_TOOLS - (
            {"apply_track_road_edit"} if live_osm_read else set()
        )
        if tool_names != expected:
            raise SystemExit(
                "installed MCP package has unexpected tools: "
                f"missing={sorted(expected - tool_names)}, extra={sorted(tool_names - expected)}"
            )
        if resources.resources:
            raise SystemExit(
                "installed MCP package unexpectedly exposes concrete resources"
            )
        template_uris = {
            template.uriTemplate for template in templates.resourceTemplates
        }
        if template_uris != EXPECTED_RESOURCE_TEMPLATES:
            raise SystemExit(
                "installed MCP package has unexpected resource templates: "
                f"{sorted(template_uris)}"
            )
        prompt_names = {item.name for item in prompts.prompts}
        if prompt_names != EXPECTED_PROMPTS:
            raise SystemExit(
                f"installed MCP package has unexpected prompts: {sorted(prompt_names)}"
            )
        if len(prompt.messages) != 1:
            raise SystemExit("review_gpx_road_edit must return one review message")
        prompt_text = getattr(prompt.messages[0].content, "text", "")
        if "complete proposal_digest" not in prompt_text:
            raise SystemExit("review prompt is missing the exact digest review gate")
        if "Do not call apply_osm_edit" not in prompt_text:
            raise SystemExit("review prompt is missing the no-apply stop condition")
        if not preview.contents or not getattr(preview.contents[0], "text", ""):
            raise SystemExit("synthetic GPX selection preview resource is empty")
        package_version = version("osm-edit-mcp")
        if initialized.serverInfo.version != package_version:
            raise SystemExit(
                "initialize serverInfo.version does not match installed package: "
                f"{initialized.serverInfo.version!r} != {package_version!r}"
            )

        print(
            "installed MCP package verified: "
            f"version={package_version}, protocol={initialized.protocolVersion}, "
            f"tools={len(tool_names)}, templates={len(template_uris)}, "
            f"prompts={len(prompt_names)}, synthetic_gpx_preview=ok"
            + (", live_osm_read=ok" if live_osm_read else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--command", required=True, help="installed console script path"
    )
    parser.add_argument(
        "--live-osm-read",
        action="store_true",
        help="also perform one read-only production API lookup for node 1",
    )
    args = parser.parse_args()
    asyncio.run(smoke_test(args.command, live_osm_read=args.live_osm_read))


if __name__ == "__main__":
    main()
