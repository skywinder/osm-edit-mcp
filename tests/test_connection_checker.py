"""The setup check must verify live identity without crossing an edit boundary."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "connection_checker", Path(__file__).parents[1] / "scripts/check_mcp_connection.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class Session:
    def __init__(self, responses, names):
        self.responses, self.names = responses, names
        self.calls = []

    async def initialize(self):
        self.calls.append("initialize")

    async def list_tools(self):
        self.calls.append("list_tools")
        return SimpleNamespace(
            tools=[SimpleNamespace(name=name) for name in self.names]
        )

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        return SimpleNamespace(isError=False, structuredContent=self.responses[name])


def editing_session():
    identity = {"username": "Mapper", "user_id": "42", "permissions": ["write_api"]}
    return Session(
        {
            "get_edit_capabilities": {
                "result": {
                    "success": True,
                    "data": {
                        "environment": "development",
                        "api_target": checker.TARGETS["development"],
                        "write_profile": "safe",
                        "raw_write_tools_registered": False,
                        "production_confirmation": {
                            "required": True,
                            "mechanism": "MCP elicitation bound to proposal SHA-256",
                        },
                        "authentication": {"status": "verified", **identity},
                    },
                }
            },
            "check_authentication": {
                "result": {
                    "success": True,
                    "authenticated": True,
                    "data": {
                        "api_url": checker.TARGETS["development"],
                        "api_mode": "Development",
                        **identity,
                    },
                }
            },
        },
        {"get_edit_capabilities", "check_authentication"},
    )


@pytest.mark.asyncio
async def test_same_session_checks_identity_and_never_writes():
    session = editing_session()
    result = await checker.verify(
        session, "edit", environment="development", username="Mapper"
    )
    assert result["user_id"] == "42"
    assert session.calls == [
        "initialize",
        "list_tools",
        "get_edit_capabilities",
        "check_authentication",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["account", "permissions", "api", "profile", "identity", "confirmation"]
)
async def test_editing_mismatches_fail_closed(failure):
    session = editing_session()
    caps = session.responses["get_edit_capabilities"]["result"]["data"]
    live = session.responses["check_authentication"]["result"]["data"]
    if failure == "account":
        live["username"] = "Another account"
    elif failure == "permissions":
        live["permissions"] = []
    elif failure == "api":
        live["api_url"] = checker.TARGETS["production"]
    elif failure == "profile":
        caps["raw_write_tools_registered"] = True
    elif failure == "identity":
        live["user_id"] = "99"
    else:
        caps["production_confirmation"]["required"] = False
    with pytest.raises(ValueError, match="verification failed"):
        await checker.verify(
            session, "edit", environment="development", username="Mapper"
        )


@pytest.mark.asyncio
async def test_discovery_probe_uses_returned_coordinates_and_ref():
    session = Session(
        {
            "resolve_location": {
                "success": True,
                "data": {"candidates": [{"location": {"lat": 40.18, "lon": 44.51}}]},
            },
            "search_nearby_places": {
                "success": True,
                "data": {"places": [{"place_ref": "osm:node:42"}]},
            },
            "get_place_details": {
                "success": True,
                "data": {"place": {"place_ref": "osm:node:42"}},
            },
        },
        checker.DISCOVERY,
    )
    calls = []
    original = session.call_tool

    async def record(name, arguments):
        calls.append((name, arguments))
        return await original(name, arguments)

    session.call_tool = record
    await checker.verify(session, "discovery", query="Public landmark")
    assert calls[1][1]["lat"] == 40.18
    assert calls[1][1]["lon"] == 44.51
    assert calls[2] == ("get_place_details", {"place_ref": "osm:node:42"})
    assert not any("auth" in name for name in session.calls)


@pytest.mark.asyncio
async def test_discovery_does_not_claim_provider_check_without_query():
    session = Session({}, checker.DISCOVERY)
    result = await checker.verify(session, "discovery")
    assert result["verified"] == "protocol and tool list only"
    assert session.calls == ["initialize", "list_tools"]


@pytest.mark.asyncio
async def test_discovery_rejects_full_profile():
    with pytest.raises(ValueError, match="exactly"):
        await checker.verify(
            Session({}, checker.DISCOVERY | {"apply_osm_edit"}), "discovery"
        )


@pytest.mark.asyncio
async def test_editing_rejects_raw_tools_even_if_capability_claims_safe():
    session = editing_session()
    session.names.add("create_osm_node")
    with pytest.raises(ValueError, match="Raw write tools"):
        await checker.verify(
            session, "edit", environment="development", username="Mapper"
        )
