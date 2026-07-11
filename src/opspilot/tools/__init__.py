"""Investigation tools.

Eight read-only tools exposed via `ToolService` (in-process now, MCP-fronted later): six
deterministic (incident/alert/deployment/logs/metrics/dependencies) over the repository, and two
retrieval tools (`search_runbooks`, `search_past_incidents`) over the hybrid Retriever.
"""

from opspilot.tools.service import ToolService

__all__ = ["ToolService"]
