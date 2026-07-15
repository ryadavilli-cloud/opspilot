"""ToolService — the in-process tool boundary the agent binds to.

Wires the read-only tools in-process over a repository (deterministic tools) and a lazily-built
`Retriever` (the two retrieval tools). `call()` is the allowlisted, dispatch-by-name shape an MCP
client uses; the MCP server (see `opspilot.mcp`) will front these same methods — transport swap,
not a rewrite. The retriever is built on first retrieval call and cached; if the retrieval extras
aren't installed, the search tools return a sanitized error rather than breaking the service.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opspilot.data.repository import Repository, default_repository
from opspilot.tools.alerts import get_correlated_alerts
from opspilot.tools.contracts import ToolResult
from opspilot.tools.dependencies import get_service_dependencies
from opspilot.tools.deployments import get_deployments
from opspilot.tools.errors import error_result
from opspilot.tools.incidents import get_incident
from opspilot.tools.logs import query_logs
from opspilot.tools.metrics import get_metrics
from opspilot.tools.search import search_past_incidents, search_runbooks

if TYPE_CHECKING:
    from opspilot.retrieval.base import SearchRetriever


class ToolService:
    def __init__(
        self,
        repo: Repository | None = None,
        retriever_factory: Callable[[], SearchRetriever] | None = None,
    ) -> None:
        self.repo = repo or default_repository()
        self._retriever_factory = retriever_factory
        self._retriever: SearchRetriever | None = None
        self._retriever_attempted = False
        self._retriever_error: str | None = None
        self._registry: dict[str, Callable[..., ToolResult[Any]]] = {
            "get_incident": self.get_incident,
            "get_correlated_alerts": self.get_correlated_alerts,
            "get_deployments": self.get_deployments,
            "query_logs": self.query_logs,
            "get_metrics": self.get_metrics,
            "get_service_dependencies": self.get_service_dependencies,
            "search_runbooks": self.search_runbooks,
            "search_past_incidents": self.search_past_incidents,
        }

    # --- deterministic tools (repository-backed) ----------------------------------------------
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

    # --- retrieval tools (retriever-backed, lazy) ---------------------------------------------
    def _get_retriever(self) -> SearchRetriever | None:
        if self._retriever is None and not self._retriever_attempted:
            self._retriever_attempted = True
            try:
                if self._retriever_factory is not None:
                    self._retriever = self._retriever_factory()
                else:
                    from opspilot.retrieval.factory import build_retriever
                    self._retriever = build_retriever(include_distractors=False)
            except Exception as exc:  # noqa: BLE001 — degrade, but retain the sanitized reason
                first_line = (str(exc).splitlines() or [""])[0][:200]
                self._retriever_error = f"{type(exc).__name__}: {first_line}"
        return self._retriever

    @property
    def retrieval_backend(self) -> str:
        """The active retrieval backend for readiness diagnostics: bm25 | hybrid | rerank, or
        `unavailable` if construction failed (see `retrieval_error` for the reason)."""
        retriever = self._get_retriever()
        return getattr(retriever, "backend_name", "unavailable") if retriever else "unavailable"

    @property
    def retrieval_error(self) -> str | None:
        """Sanitized retriever-initialization error, if any (class + first line). None when
        retrieval is healthy — for readiness checks, not tool output."""
        self._get_retriever()
        return self._retriever_error

    def search_runbooks(self, **kwargs: Any) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return error_result("search_runbooks", "retrieval unavailable", time.perf_counter())
        return search_runbooks(retriever, **kwargs)

    def search_past_incidents(self, **kwargs: Any) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return error_result(
                "search_past_incidents", "retrieval unavailable", time.perf_counter())
        return search_past_incidents(retriever, self.repo, **kwargs)

    # --- dispatch -----------------------------------------------------------------------------
    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._registry)

    def call(self, tool_name: str, **kwargs: Any) -> ToolResult[Any]:
        """Dispatch by name against the allowlist; an unknown name is a sanitized error."""
        fn = self._registry.get(tool_name)
        if fn is None:
            return error_result(tool_name or "unknown", "unknown tool", time.perf_counter())
        return fn(**kwargs)
