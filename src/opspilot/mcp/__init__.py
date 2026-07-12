"""MCP boundary — a transport over the existing ToolService, not a second implementation.

`server.py` exposes a subset of `ToolService.call()` through MCP: schemas are generated from the
existing Pydantic request models, and every call is dispatched through `ToolService.call()`, so the
allowlist and validation are shared with the in-process path (proven by a parity test). New tools
are added by registration, not custom handlers. No auth / remote hosting yet.
"""
