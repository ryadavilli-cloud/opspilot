"""MCP server fronting ToolService — transport swap, not a rewrite.

Exposes a subset of the tools over MCP. Each tool advertises the JSON schema generated from its
existing Pydantic request model; the actual call goes through `ToolService.call()`, so validation
and the allowlist are exactly the in-process ones. Add a tool by adding it to EXPOSED_TOOLS.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from mcp.server import Server
from mcp.types import TextContent, Tool
from pydantic import BaseModel

from opspilot.tools.contracts import (
    ExecutionOutcome,
    GetIncidentRequest,
    GetLogsRequest,
    SearchRunbooksRequest,
)
from opspilot.tools.errors import error_result
from opspilot.tools.service import ToolService

# Start small; expand by registration. Value = the Pydantic request model (schema source).
EXPOSED_TOOLS: dict[str, type[BaseModel]] = {
    "get_incident": GetIncidentRequest,
    "query_logs": GetLogsRequest,
    "search_runbooks": SearchRunbooksRequest,
}

# The SDK's two handler-registration decorators carry no annotations, so their types are stated
# here instead. Both register a handler and return the decorated function unchanged, which is what
# these shapes say; neither wraps or replaces it, so nothing about the handlers below is affected.
type _ListToolsHandler = Callable[[], Awaitable[list[Tool]]]
type _CallToolHandler = Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]


class _RegisterListTools(Protocol):
    def __call__(self) -> Callable[[_ListToolsHandler], _ListToolsHandler]: ...


class _RegisterCallTool(Protocol):
    def __call__(
        self, *, validate_input: bool = True
    ) -> Callable[[_CallToolHandler], _CallToolHandler]: ...


def build_server(service: ToolService | None = None) -> Server:
    svc = service or ToolService()
    server: Server = Server("opspilot-tools")
    register_list_tools = cast(_RegisterListTools, server.list_tools)
    register_call_tool = cast(_RegisterCallTool, server.call_tool)

    @register_list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=f"OpsPilot read-only tool: {name}",
                inputSchema=model.model_json_schema(),
            )
            for name, model in EXPOSED_TOOLS.items()
        ]

    # validate_input=False: let ToolService.call() do the validation, so it is identical to the
    # in-process path (same Pydantic models, same sanitized error envelope).
    @register_call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in EXPOSED_TOOLS:
            result = error_result(
                name or "unknown", "unknown tool", time.perf_counter(), ExecutionOutcome.REJECTED
            )
        else:
            result = svc.call(name, **(arguments or {}))
        return [TextContent(type="text", text=result.model_dump_json())]

    return server


def run() -> None:  # pragma: no cover - real stdio server process
    import anyio
    from mcp.server.stdio import stdio_server

    async def _serve() -> None:
        server = build_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_serve)


if __name__ == "__main__":  # pragma: no cover
    run()
