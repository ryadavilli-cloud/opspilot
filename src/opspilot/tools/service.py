"""ToolService — the in-process tool boundary the agent binds to.

Phase 3 wires the three tools in-process over a repository. At Phase 8, an MCP server (see
`opspilot.mcp`) fronts these same methods for the external-system tools; the agent's contract does
not change — only the transport is swapped. `call()` is the allowlisted, dispatch-by-name shape an
MCP client uses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from opspilot.data.repository import Repository, default_repository
from opspilot.tools.alerts import get_correlated_alerts
from opspilot.tools.contracts import ToolResult
from opspilot.tools.dependencies import get_service_dependencies
from opspilot.tools.deployments import get_deployments
from opspilot.tools.errors import error_result
from opspilot.tools.incidents import get_incident
from opspilot.tools.logs import query_logs
from opspilot.tools.metrics import get_metrics


class ToolService:
    def __init__(self, repo: Repository | None = None) -> None:
        self.repo = repo or default_repository()
        self._registry: dict[str, Callable[..., ToolResult[Any]]] = {
            "get_incident": get_incident,
            "get_correlated_alerts": get_correlated_alerts,
            "get_deployments": get_deployments,
            "query_logs": query_logs,
            "get_metrics": get_metrics,
            "get_service_dependencies": get_service_dependencies,
        }

    def get_incident(self, **kwargs: Any) -> ToolResult[Any]:
        return get_incident(self.repo, **kwargs)

    def get_correlated_alerts(self, **kwargs: Any) -> ToolResult[Any]:
        return get_correlated_alerts(self.repo, **kwargs)

    def get_deployments(self, **kwargs: Any) -> ToolResult[Any]:
        return get_deployments(self.repo, **kwargs)

    def query_logs(self, **kwargs: Any) -> ToolResult[Any]:
        return query_logs(self.repo, **kwargs)

    def get_metrics(self, **kwargs: Any) -> ToolResult[Any]:
        return get_metrics(self.repo, **kwargs)

    def get_service_dependencies(self, **kwargs: Any) -> ToolResult[Any]:
        return get_service_dependencies(self.repo, **kwargs)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._registry)

    def call(self, tool_name: str, **kwargs: Any) -> ToolResult[Any]:
        """Dispatch by name against the allowlist; an unknown name is a sanitized error."""
        fn = self._registry.get(tool_name)
        if fn is None:
            return error_result(tool_name or "unknown", "unknown tool", time.perf_counter())
        return fn(self.repo, **kwargs)
