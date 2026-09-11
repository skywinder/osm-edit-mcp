#!/usr/bin/env python3
"""Verify one configured stdio session without editing OSM or printing secrets."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DISCOVERY = {"resolve_location", "search_nearby_places", "get_place_details"}
RAW_WRITES = {
    "create_changeset",
    "close_changeset",
    "create_osm_node",
    "create_osm_way",
    "create_osm_relation",
    "update_osm_node",
    "update_osm_way",
    "update_osm_relation",
    "delete_osm_node",
    "delete_osm_way",
    "delete_osm_relation",
    "create_place_from_description",
    "find_and_update_place",
    "delete_place_from_description",
    "bulk_create_places",
}
TARGETS = {
    "development": "https://api06.dev.openstreetmap.org/api/0.6",
    "production": "https://api.openstreetmap.org/api/0.6",
}


async def payload(session, name, arguments=None):
    response = await session.call_tool(name, arguments or {})
    if response.isError:
        raise ValueError(f"{name} returned an error")
    data = response.structuredContent
    if data is None:
        data = json.loads(next(c.text for c in response.content if c.type == "text"))
    data = data.get("result", data)  # Legacy FastMCP Dict result envelope.
    if data.get("success") is not True:
        raise ValueError(f"{name} did not succeed")
    return data


async def verify(session, mode, query=None, environment=None, username=None):
    await session.initialize()
    names = {tool.name for tool in (await session.list_tools()).tools}
    if mode == "discovery":
        if names != DISCOVERY:
            raise ValueError("Expected exactly the three discovery tools")
        if not query:
            return {"profile": mode, "verified": "protocol and tool list only"}
        resolved = (await payload(session, "resolve_location", {"query": query}))[
            "data"
        ]
        candidates = resolved["candidates"]
        if len(candidates) != 1:
            raise ValueError("Location is empty or ambiguous; use a more precise query")
        places = (
            await payload(
                session,
                "search_nearby_places",
                {
                    **candidates[0]["location"],
                    "radius_meters": 300,
                    "categories": ["cafe", "pharmacy"],
                    "limit": 3,
                },
            )
        )["data"]["places"]
        if not places:
            raise ValueError("No nearby probe matches; choose another location")
        ref = places[0]["place_ref"]
        details = (await payload(session, "get_place_details", {"place_ref": ref}))[
            "data"
        ]
        if details["place"]["place_ref"] != ref:
            raise ValueError("Details do not match the selected place")
        return {"profile": mode, "verified": "resolve, nearby search, details"}
    if environment not in TARGETS or not username:
        raise ValueError(
            "Editing verification requires expected environment and username"
        )
    if not {"get_edit_capabilities", "check_authentication"} <= names:
        raise ValueError("Editing diagnostics are unavailable")
    if names & RAW_WRITES:
        raise ValueError("Raw write tools must be absent")
    caps = (await payload(session, "get_edit_capabilities"))["data"]
    auth = await payload(session, "check_authentication")
    identity, live = caps["authentication"], auth["data"]
    confirmation = caps["production_confirmation"]
    if not (
        caps["environment"] == environment
        and caps["api_target"].rstrip("/") == TARGETS[environment]
        and live["api_url"].rstrip("/") == TARGETS[environment]
        and live["api_mode"].lower() == environment
        and caps["write_profile"] == "safe"
        and caps["raw_write_tools_registered"] is False
        and confirmation["required"] is True
        and confirmation["mechanism"] == "MCP elicitation bound to proposal SHA-256"
        and identity["status"] == "verified"
        and auth["authenticated"] is True
        and identity["username"] == live["username"] == username
        and identity["user_id"] == live["user_id"]
        and identity["user_id"]
        and "write_api" in identity["permissions"]
        and "write_api" in live["permissions"]
    ):
        raise ValueError(
            "API, identity, permission, or safety-profile verification failed"
        )
    return {
        "profile": "full/safe",
        "environment": environment,
        "username": username,
        "user_id": live["user_id"],
        "verified": "live authentication; no edit performed",
    }


async def run(args):
    config = json.loads(Path(args.server_config).read_text())
    if not isinstance(config, dict) or set(config) - {"command", "args", "env"}:
        raise ValueError("Use one server record containing command, args, and env")
    if not isinstance(config.get("command"), str) or not config["command"]:
        raise ValueError("command must be a nonempty string")
    if not isinstance(config.get("args", []), list) or any(
        not isinstance(value, str) for value in config.get("args", [])
    ):
        raise ValueError("args must be a list of strings")
    if not isinstance(config.get("env", {}), dict) or any(
        not isinstance(value, str) for value in config.get("env", {}).values()
    ):
        raise ValueError("env values must be strings")
    params = StdioServerParameters(**config)
    # Server stderr can contain host-local details. This check only prints its
    # own summary; use the host's private diagnostic log for startup failures.
    with open(os.devnull, "w") as errors, anyio.fail_after(120):
        async with stdio_client(params, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                return await verify(
                    session,
                    args.mode,
                    args.query,
                    args.expect_environment,
                    args.expect_user,
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-config", required=True)
    parser.add_argument("--mode", choices=["discovery", "edit"], required=True)
    parser.add_argument(
        "--query", help="Optional public location for a discovery probe"
    )
    parser.add_argument("--expect-environment", choices=list(TARGETS))
    parser.add_argument("--expect-user")
    args = parser.parse_args()
    if args.mode == "edit" and not (args.expect_environment and args.expect_user):
        parser.error("edit requires --expect-environment and --expect-user")
    try:
        print(json.dumps(asyncio.run(run(args)), ensure_ascii=False))
    except Exception:
        # Exception groups and upstream errors may embed credentials/URLs.
        print(
            "MCP verification failed; inspect configuration and private host logs.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
