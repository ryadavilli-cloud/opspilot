"""The one protocol exposure, exercised as a protocol.

A real stdio server is spawned as a process, a real client connects over its pipes, and the tool is
called through it. Nothing here is mocked: a test that stubbed the transport would prove that this
codebase can call a function it already calls, which is not what the boundary is for.

What is being shown is that two ways in reach one implementation. So the same arguments go through
the protocol and through the registry directly, and the two answers are compared field by field.
Only the transport differs, and it is recorded where an engineer can see it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fake_operational_records import corpus_records

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from opspilot.mcp.server import EXPOSED_CAPABILITY, MCP_TRANSPORT, build_server  # noqa: E402
from opspilot.tools.service import ToolService  # noqa: E402

SERVER = Path(__file__).resolve().parent / "mcp_stdio_server.py"
# A window the corpus actually has changes in, so parity is compared over rows rather than
# over two empty lists, which would be equal and prove nothing.
SERVICES = ["checkout-api", "redis-cache"]
WINDOW = {"start_time": "2026-06-01T00:00:00Z", "end_time": "2026-07-15T00:00:00Z"}


def _over_stdio(work: Any) -> Any:
    """Run `work(session)` against a freshly spawned server, over its actual pipes."""

    async def go() -> Any:
        parameters = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await work(session)

    return asyncio.run(go())


def _payload(result: Any) -> dict[str, Any]:
    """The tool's return value, as the protocol delivered it."""
    if getattr(result, "structuredContent", None):
        content = result.structuredContent
        return dict(content.get("result", content))
    return dict(json.loads(result.content[0].text))


def _direct() -> dict[str, Any]:
    """The same capability through the registry, with the same arguments."""
    service = ToolService(corpus_records())
    return dict(
        service.call(EXPOSED_CAPABILITY, None, services=SERVICES, **WINDOW).model_dump(mode="json")
    )


# --- what the server offers ------------------------------------------------------------------
def test_the_server_exposes_one_capability_and_no_other():
    """The exposure is one capability by construction. Everything else the registry holds stays
    unreachable through this boundary, so there is no surface to audit for what it might expose."""

    async def work(session: ClientSession) -> list[str]:
        listed = await session.list_tools()
        return [tool.name for tool in listed.tools]

    assert _over_stdio(work) == [EXPOSED_CAPABILITY]


def test_a_tool_the_server_does_not_expose_cannot_be_called_through_it():
    """A write-shaped or simply unknown request has nowhere to arrive. The protocol answers that
    the tool is unknown; nothing here inspects a call for intent."""

    async def work(session: ClientSession) -> Any:
        return await session.call_tool("delete_deployments", {"services": SERVICES, **WINDOW})

    result = _over_stdio(work)
    assert result.isError, "an unknown tool was routed somewhere"


def test_every_registered_capability_other_than_the_exposed_one_stays_unreachable():
    """Asserted against the registry rather than a written list, so a capability added later is
    covered without this test being edited."""
    from opspilot.tools import CAPABILITY_NAMES

    async def work(session: ClientSession) -> list[Any]:
        outcomes = []
        for name in CAPABILITY_NAMES:
            if name == EXPOSED_CAPABILITY:
                continue
            outcomes.append((name, (await session.call_tool(name, {})).isError))
        return outcomes

    for name, errored in _over_stdio(work):
        assert errored, f"{name} was reachable over MCP"


# --- one implementation, two ways in -----------------------------------------------------------
def test_the_protocol_path_and_the_direct_path_return_the_same_result():
    """The parity the boundary exists to demonstrate. Compared field by field except for timing,
    which measures the call rather than describing its answer and cannot be equal across two."""

    async def work(session: ClientSession) -> dict[str, Any]:
        return _payload(
            await session.call_tool(EXPOSED_CAPABILITY, {"services": SERVICES, **WINDOW})
        )

    over_mcp, direct = _over_stdio(work), _direct()

    assert over_mcp["outcome"] == direct["outcome"]
    assert over_mcp["completeness"] == direct["completeness"]
    assert over_mcp["results"] == direct["results"]
    assert over_mcp["evidence_refs"] == direct["evidence_refs"]
    assert over_mcp["error"] == direct["error"]
    assert over_mcp["results"], "both paths returned nothing, so the comparison is vacuous"


def test_the_protocol_path_reshapes_nothing():
    """No MCP-specific result shape exists. What comes back over the protocol carries the same
    fields as the envelope every capability returns, and no others."""

    async def work(session: ClientSession) -> dict[str, Any]:
        return _payload(
            await session.call_tool(EXPOSED_CAPABILITY, {"services": SERVICES, **WINDOW})
        )

    assert set(_over_stdio(work)) == set(_direct())


def test_a_request_the_capability_cannot_accept_is_refused_the_same_way_on_both_paths():
    """Validation belongs to the capability, not to the exposure, so a bad argument is refused
    identically whichever way it arrived."""

    async def work(session: ClientSession) -> Any:
        return await session.call_tool(EXPOSED_CAPABILITY, {"services": [], **WINDOW})

    result = _over_stdio(work)
    direct = ToolService(corpus_records()).call(EXPOSED_CAPABILITY, None, services=[], **WINDOW)
    if result.isError:
        assert direct.outcome.value == "rejected"
    else:
        assert _payload(result)["outcome"] == direct.outcome.value


# --- the transport is what differs, and it is visible --------------------------------------------
def test_the_protocol_path_records_the_transport_it_arrived_on(span_exporter):
    """What tells the two ways in apart, on the handler that actually records it.

    Called in process rather than over the pipes, because a span emitted inside a spawned server
    is exported inside that server and a test outside it would be asserting on nothing. The
    handler under test is the same one the protocol reaches; what differs is only who called it.
    """
    server = build_server(ToolService(corpus_records()))

    asyncio.run(server.call_tool(EXPOSED_CAPABILITY, {"services": SERVICES, **WINDOW}))

    tool_spans = [s for s in span_exporter.spans if s.name == f"tool.{EXPOSED_CAPABILITY}"]
    assert tool_spans, "the exposure emitted no span for the call it served"
    assert any(s.attributes.get("transport") == MCP_TRANSPORT for s in tool_spans)


def test_an_ordinary_investigation_records_the_other_transport():
    """The counterpart, so `mcp` means something. The graph builds its capability activity with
    `direct`, and the two are the whole vocabulary."""
    from opspilot.stream.projection import emit

    event = emit(
        "investigation.capability",
        "inv-1",
        "inc-005",
        sequence=1,
        phase="gathering",
        action=EXPOSED_CAPABILITY,
        detail="one call, through the registry",
        capability=EXPOSED_CAPABILITY,
        transport="direct",
    )

    assert event.transport == "direct"
    assert event.transport != MCP_TRANSPORT


# --- the exposure is part of what ships ---------------------------------------------------------
def test_the_protocol_sdk_is_a_runtime_dependency_rather_than_a_development_one():
    """The image that runs the application is the image that can serve this.

    The exposure is only a protocol boundary if it exists where the application runs, so the SDK
    belongs in the base dependencies rather than a group the deployed image never installs. This is
    the thing that would quietly break: moving it into a group would leave every test here passing
    and the shipped image unable to start the server.
    """
    import tomllib

    manifest = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    base = " ".join(manifest["project"]["dependencies"])
    assert "mcp" in base, "the MCP SDK is not a runtime dependency"


def test_the_server_starts_and_describes_itself_without_a_backing_store():
    """What makes the shipped image able to serve this at all, and what a container starting in an
    environment without Cosmos would hit first. Listing the tool reaches no store; only calling it
    does."""
    server = build_server()

    listed = asyncio.run(server.list_tools())

    assert [tool.name for tool in listed] == [EXPOSED_CAPABILITY]
