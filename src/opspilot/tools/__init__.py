"""Investigation tools.

Phase 3 real tools: `get_incident`, `get_correlated_alerts`, `get_deployments`, exposed via
`ToolService` (in-process now, MCP-fronted at Phase 8). `search_runbooks`/`search_past_incidents`
remain stubs (stubs.py) until the RAG phase.
"""

from opspilot.tools.service import ToolService

__all__ = ["ToolService"]
