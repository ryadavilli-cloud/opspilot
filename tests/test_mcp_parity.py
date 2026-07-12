"""Step 4 gate: the MCP transport is equivalent to the in-process ToolService.

Calls each exposed tool (1) directly through ToolService and (2) through an in-memory MCP
client/server, and asserts equivalent status, results, and evidence references — proving MCP is a
transport over the same service, not a second implementation. (metadata.duration_ms is excluded —
it's timing, not payload.)
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from opspilot.mcp.server import EXPOSED_TOOLS, build_server
from opspilot.tools.service import ToolService


def _via_mcp(server, name: str, arguments: dict) -> dict:
    async def _go() -> dict:
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool(name, arguments)
            return json.loads(result.content[0].text)

    return asyncio.run(_go())


def _assert_parity(svc: ToolService, server, name: str, arguments: dict) -> None:
    direct = svc.call(name, **arguments)
    over_mcp = _via_mcp(server, name, arguments)
    direct_json = json.loads(direct.model_dump_json())
    assert over_mcp["status"] == direct.status
    assert over_mcp["evidence_refs"] == direct.evidence_refs
    assert over_mcp["results"] == direct_json["results"]
    assert over_mcp["error"] == direct.error


def test_list_tools_exposes_the_registered_set():
    server = build_server()

    async def _go() -> set[str]:
        async with create_connected_server_and_client_session(server) as client:
            listed = await client.list_tools()
            return {t.name for t in listed.tools}

    assert asyncio.run(_go()) == set(EXPOSED_TOOLS)


def test_parity_deterministic_tools():
    svc = ToolService()
    server = build_server(svc)
    _assert_parity(svc, server, "get_incident", {"incident_id": "inc-001"})
    _assert_parity(svc, server, "get_incident", {"incident_id": "inc-999"})     # empty result
    _assert_parity(svc, server, "get_incident", {"incident_id": ""})            # validation error
    _assert_parity(svc, server, "query_logs", {
        "service": "payment-api",
        "start_time": "2026-06-28T09:45:00Z", "end_time": "2026-06-28T10:45:00Z",
    })


def test_mcp_rejects_unexposed_tool():
    server = build_server()
    over_mcp = _via_mcp(server, "get_metrics", {"service": "cosmos-db"})  # real tool, not exposed
    assert over_mcp["status"] == "error" and over_mcp["error"] == "unknown tool"


def test_parity_retrieval_tool():
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("rank_bm25")
    svc = ToolService()
    server = build_server(svc)
    _assert_parity(svc, server, "search_runbooks", {"query": "payment authorizations timing out"})
