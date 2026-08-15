"""ToolService — the in-process tool boundary the agent binds to.

Wires the read-only capabilities in-process over the `operational-records` container (the six
deterministic capabilities) and a lazily-built `Retriever` over the `knowledge` container (the two
retrieval capabilities). `call()` is the allowlisted, dispatch-by-name shape an MCP client uses; the
MCP server (see `opspilot.mcp`) fronts these same methods: transport swap, not a rewrite. The
retriever is built on first retrieval call and cached; if it cannot be reached (Cosmos or the
embedding deployment unavailable), the search tools return a sanitized `unavailable` rather than
breaking the service.

Every capability call carries a deadline this service supplies. The deadline is a bound, so it is
established by deterministic code and is unreachable from a prompt (`code-guidelines.md` §7): a
request naming its own `deadline_s` is refused at dispatch rather than honored or silently dropped.
Until the turn controller owns the turn's remaining time, the configured ceiling supplies it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opspilot import config
from opspilot.data.operational_records import OperationalRecords, default_operational_records
from opspilot.tools.alerts import get_correlated_alerts
from opspilot.tools.contracts import ExecutionOutcome, ToolResult
from opspilot.tools.dependencies import get_service_dependencies
from opspilot.tools.deployments import get_deployments
from opspilot.tools.errors import error_result
from opspilot.tools.incidents import get_incident
from opspilot.tools.logs import query_logs
from opspilot.tools.metrics import get_metrics
from opspilot.tools.search import search_past_incidents, search_runbooks
from opspilot.tools.structured_query import ALL_COLLECTIONS, structured_query

if TYPE_CHECKING:
    from opspilot.retrieval.retriever import Retriever

# The one parameter name a caller may never supply. It is a bound, not an argument.
_DEADLINE_PARAMETER = "deadline_s"


class ToolService:
    def __init__(
        self,
        records: OperationalRecords | None = None,
        retriever_factory: Callable[[], Retriever] | None = None,
        *,
        deadline_s: float | None = None,
        granted_collections: frozenset[str] = ALL_COLLECTIONS,
    ) -> None:
        self.records = records if records is not None else default_operational_records()
        self.deadline_s = deadline_s if deadline_s is not None else config.SOURCE_DEADLINE_SECONDS
        self.granted_collections = granted_collections
        self._retriever_factory = retriever_factory
        self._retriever: Retriever | None = None
        self._retriever_attempted = False
        self._retriever_error: str | None = None
        # Built against the one capability inventory, so the registry cannot drift from it. A
        # name in the inventory with no implementation here is a defect, not a silent omission.
        from opspilot.tools import CAPABILITY_NAMES

        self._registry: dict[str, Callable[..., ToolResult[Any]]] = {
            name: getattr(self, name) for name in CAPABILITY_NAMES
        }

    # --- deterministic capabilities (operational-records container) ---------------------------
    def get_incident(self, **kwargs: Any) -> ToolResult[Any]:
        return get_incident(self.records, deadline_s=self.deadline_s, **kwargs)

    def get_correlated_alerts(self, **kwargs: Any) -> ToolResult[Any]:
        return get_correlated_alerts(self.records, deadline_s=self.deadline_s, **kwargs)

    def get_deployments(self, **kwargs: Any) -> ToolResult[Any]:
        return get_deployments(self.records, deadline_s=self.deadline_s, **kwargs)

    def query_logs(self, **kwargs: Any) -> ToolResult[Any]:
        return query_logs(self.records, deadline_s=self.deadline_s, **kwargs)

    def get_metrics(self, **kwargs: Any) -> ToolResult[Any]:
        return get_metrics(self.records, deadline_s=self.deadline_s, **kwargs)

    def get_service_dependencies(self, **kwargs: Any) -> ToolResult[Any]:
        return get_service_dependencies(self.records, deadline_s=self.deadline_s, **kwargs)

    def structured_query(self, **kwargs: Any) -> ToolResult[Any]:
        # The grant is supplied here, alongside the deadline and for the same reason: both bound
        # what a request may reach, so neither is a value a request carries.
        return structured_query(
            self.records, deadline_s=self.deadline_s, granted=self.granted_collections, **kwargs
        )

    # --- retrieval tools (retriever-backed, lazy) ---------------------------------------------
    def _get_retriever(self) -> Retriever | None:
        if self._retriever is None and not self._retriever_attempted:
            self._retriever_attempted = True
            try:
                if self._retriever_factory is not None:
                    self._retriever = self._retriever_factory()
                else:
                    from opspilot.retrieval.retriever import default_retriever

                    self._retriever = default_retriever()
            except Exception as exc:  # noqa: BLE001 — degrade, but retain the sanitized reason
                first_line = (str(exc).splitlines() or [""])[0][:200]
                self._retriever_error = f"{type(exc).__name__}: {first_line}"
        return self._retriever

    @property
    def retrieval_backend(self) -> str:
        """`config.RETRIEVAL_BACKEND` when the retriever is reachable, `unavailable` if
        construction failed (see `retrieval_error` for the reason), for readiness diagnostics."""
        retriever = self._get_retriever()
        return config.RETRIEVAL_BACKEND if retriever is not None else "unavailable"

    @property
    def retrieval_error(self) -> str | None:
        """Sanitized retriever-initialization error, if any (class + first line). None when
        retrieval is healthy — for readiness checks, not tool output."""
        self._get_retriever()
        return self._retriever_error

    def search_runbooks(self, **kwargs: Any) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return self._unavailable("search_runbooks")
        return search_runbooks(retriever, deadline_s=self.deadline_s, **kwargs)

    def search_past_incidents(self, **kwargs: Any) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return self._unavailable("search_past_incidents")
        return search_past_incidents(retriever, deadline_s=self.deadline_s, **kwargs)

    @staticmethod
    def _unavailable(tool_name: str) -> ToolResult[Any]:
        """The source could not be reached. Distinct from a source that answered with nothing:
        one leaves the question open, the other settles it."""
        return error_result(
            tool_name, "retrieval unavailable", time.perf_counter(), ExecutionOutcome.UNAVAILABLE
        )

    # --- dispatch -----------------------------------------------------------------------------
    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._registry)

    def call(self, tool_name: str, **kwargs: Any) -> ToolResult[Any]:
        """Dispatch by name against the allowlist; an unknown name is a sanitized error."""
        fn = self._registry.get(tool_name)
        if fn is None:
            # Refused at the boundary before anything executed, which is `rejected` rather than a
            # failure: nothing ran, so there is nothing that could have gone wrong.
            return error_result(
                tool_name or "unknown",
                "unknown tool",
                time.perf_counter(),
                ExecutionOutcome.REJECTED,
            )
        if _DEADLINE_PARAMETER in kwargs:
            # A caller trying to set its own bound is refused rather than ignored. Dropping it
            # quietly would leave the request looking honored, and this is the parameter a model
            # would reach for to buy itself more time.
            return error_result(
                tool_name,
                "a request may not set its own deadline",
                time.perf_counter(),
                ExecutionOutcome.REJECTED,
            )
        return fn(**kwargs)
