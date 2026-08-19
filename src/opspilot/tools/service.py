"""ToolService: the in-process capability registry the agents reach evidence through.

Wires the read-only capabilities in-process over the `operational-records` container (the six
deterministic capabilities and the governed structured query) and a lazily-built `Retriever` over
the `knowledge` container (the two retrieval capabilities). `call()` is the allowlisted,
dispatch-by-name shape; a capability is reachable only by being registered here, and registration
is a static mapping with no discovery. The retriever is built on first retrieval call and cached;
if it cannot be reached (Cosmos or the embedding deployment unavailable), the search capabilities
return a sanitized `unavailable` rather than breaking the service.

Every capability is invoked through `run_tool`, which is where its typed parameters become its
validation and where what happened becomes the two-axis envelope. There is no request model per
capability: the implementation's parameter list is the contract, and an argument that does not fit
it is refused before the body runs.

Every call also carries a deadline this service supplies. The deadline is a bound, so it is
established by deterministic code and is unreachable from a prompt: a request naming its own
`deadline_s` is refused at dispatch rather than honored or silently dropped. Until the investigation
owns its remaining time, the configured ceiling supplies it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opspilot import config
from opspilot.data.operational_records import OperationalRecords, default_operational_records
from opspilot.data.structured_query import APPROVED_SURFACE, PredicateOp
from opspilot.tools.alerts import get_correlated_alerts
from opspilot.tools.contracts import ExecutionOutcome, ToolResult
from opspilot.tools.dependencies import get_service_dependencies
from opspilot.tools.deployments import get_deployments
from opspilot.tools.errors import error_result, run_tool
from opspilot.tools.incidents import get_incident
from opspilot.tools.logs import query_logs
from opspilot.tools.metrics import get_metrics
from opspilot.tools.search import search_past_incidents, search_runbooks
from opspilot.tools.structured_query import ALL_COLLECTIONS, structured_query

if TYPE_CHECKING:
    from opspilot.retrieval.retriever import Retriever

# The one parameter name a caller may never supply. It is a bound, not an argument.
_DEADLINE_PARAMETER = "deadline_s"

# The implementation behind each registered name. The registry below dispatches through the bound
# methods, which take `**kwargs`; this holds the implementations themselves, because their typed
# parameters are the contract and an agent proposing a call has to be told what that contract is.
# A capability the Evidence Investigator cannot describe is one it can only guess at, and a guessed
# argument is refused at the boundary, which spends a step and teaches it nothing.
_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "get_incident": get_incident,
    "get_correlated_alerts": get_correlated_alerts,
    "get_deployments": get_deployments,
    "query_logs": query_logs,
    "get_metrics": get_metrics,
    "get_service_dependencies": get_service_dependencies,
    "search_runbooks": search_runbooks,
    "search_past_incidents": search_past_incidents,
    "structured_query": structured_query,
}

# What the service supplies itself, so neither appears as an argument anyone may state.
_SUPPLIED_PARAMETERS = frozenset({"records", "retriever", "granted", _DEADLINE_PARAMETER})


def capability_arguments(name: str) -> str:
    """One capability's arguments, as a caller must state them: required bare, optional bracketed.

    Read from the implementation's own signature rather than a description kept beside it, so the
    two cannot drift and a parameter change reaches the agent that has to satisfy it.
    """
    import inspect

    implementation = _IMPLEMENTATIONS.get(name)
    if implementation is None:
        return ""
    parts = []
    for parameter in inspect.signature(implementation).parameters.values():
        if parameter.name in _SUPPLIED_PARAMETERS or parameter.kind is parameter.VAR_KEYWORD:
            continue
        required = parameter.default is inspect.Parameter.empty
        parts.append(parameter.name if required else f"[{parameter.name}]")
    return ", ".join(parts)


def capability_purpose(name: str) -> str:
    """One capability's purpose, as the caller choosing between them needs it.

    Read from the implementation's own docstring, for the same reason the arguments are read from
    its signature: the capability is the one thing that knows what it answers, and a description
    kept beside it would be a second list to fall out of date. A capability that says nothing about
    itself offers nothing here rather than a placeholder, because an empty line is honest and an
    invented one is not.
    """
    implementation = _IMPLEMENTATIONS.get(name)
    summary = (getattr(implementation, "__doc__", "") or "").strip()
    if not summary:
        return ""
    # The first paragraph, rewrapped onto one line: a docstring wraps for the file it lives in and
    # the offering is a single line per capability.
    first = summary.split("\n\n")[0]
    return " ".join(first.split())


def structured_query_surface() -> str:
    """The structure the structured query takes, for a caller that has to propose one.

    Every other capability takes flat arguments its signature can state, so `capability_arguments`
    is enough for them. This one takes a structure, and a caller told only that would have to guess
    the collections, the field names, the operators, and the ceiling. Guessing produces a refusal,
    which spends a call and teaches the caller nothing it could not have been told.

    Nothing here is written down twice. The collections, fields, and types come out of the approved
    surface, the operators out of their own enumeration, and the ceiling out of the configuration,
    all at call time: adding a field changes what a caller is told without this function being
    touched. The operand grouping mirrors the validator's own branches by naming the same enum
    members it branches on, so an operator added later is listed automatically and described by the
    same default the validator would apply to it.

    The full approved surface is rendered rather than the narrower grant a run may hold. The grant
    belongs to the service and is not in scope where a prompt is assembled, and reaching for it
    from here would be the new seam this arrangement exists to avoid. A proposal against a
    granted-out collection is refused by validation, which is where the grant is enforced anyway.
    """
    by_operand: dict[str, list[str]] = {}
    for op in PredicateOp:
        if op is PredicateOp.IN:
            form = "values"
        elif op is PredicateOp.BETWEEN:
            form = "low and high"
        elif op in (PredicateOp.PRESENT, PredicateOp.ABSENT):
            form = "no operand"
        else:
            form = "value"
        by_operand.setdefault(form, []).append(op.value)

    lines = [
        "structured_query takes a structure rather than flat arguments:",
        "  collection: exactly one of " + ", ".join(sorted(APPROVED_SURFACE)),
        "  predicates: a list of {field, op, and its operand}, combined with AND.",
        *(
            f"    {', '.join(ops)} {'take' if len(ops) > 1 else 'takes'} {form}."
            for form, ops in by_operand.items()
        ),
        '  either projection (a list of field names) or aggregate: "count", never both.',
        f"  limit: a positive integer, at most {config.STRUCTURED_QUERY_MAX_LIMIT}.",
        "  Readable fields, by collection:",
    ]
    for collection in sorted(APPROVED_SURFACE):
        stated = ", ".join(
            f"{name} ({kind.value})" for name, kind in APPROVED_SURFACE[collection].items()
        )
        lines.append(f"    {collection}: {stated}")
    return "\n".join(lines)


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

    def _within(self, remaining_s: float | None) -> float:
        """The deadline one call may take: the configured source ceiling, or the investigation's
        remaining time where that is shorter.

        Two bounds, and a call is subject to both. The ceiling keeps any single source from hanging;
        the remaining time keeps the sum of them inside the investigation, so a call started with
        seconds left cannot run for the full ceiling and outlive the run that asked for it. Passed
        in per call rather than held here, because this service is process-wide and a deadline
        stored on it would belong to whichever investigation wrote it last.
        """
        if remaining_s is None:
            return self.deadline_s
        return max(0.0, min(self.deadline_s, remaining_s))

    # --- deterministic capabilities (operational-records container) ---------------------------
    def get_incident(self, remaining_s: float | None = None, /, **kwargs: Any) -> ToolResult[Any]:
        return run_tool(
            "get_incident", get_incident, self.records, self._within(remaining_s), **kwargs
        )

    def get_correlated_alerts(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        return run_tool(
            "get_correlated_alerts",
            get_correlated_alerts,
            self.records,
            self._within(remaining_s),
            **kwargs,
        )

    def get_deployments(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        return run_tool(
            "get_deployments", get_deployments, self.records, self._within(remaining_s), **kwargs
        )

    def query_logs(self, remaining_s: float | None = None, /, **kwargs: Any) -> ToolResult[Any]:
        return run_tool("query_logs", query_logs, self.records, self._within(remaining_s), **kwargs)

    def get_metrics(self, remaining_s: float | None = None, /, **kwargs: Any) -> ToolResult[Any]:
        return run_tool(
            "get_metrics", get_metrics, self.records, self._within(remaining_s), **kwargs
        )

    def get_service_dependencies(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        return run_tool(
            "get_service_dependencies",
            get_service_dependencies,
            self.records,
            self._within(remaining_s),
            **kwargs,
        )

    def structured_query(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        # The grant is supplied here, alongside the deadline and for the same reason: both bound
        # what a request may reach, so neither is a value a request carries.
        return run_tool(
            "structured_query",
            structured_query,
            self.records,
            self._within(remaining_s),
            self.granted_collections,
            **kwargs,
        )

    # --- retrieval capabilities (retriever-backed, lazy) ---------------------------------------
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

    def search_runbooks(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return self._unavailable("search_runbooks")
        return run_tool(
            "search_runbooks", search_runbooks, retriever, self._within(remaining_s), **kwargs
        )

    def search_past_incidents(
        self, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        retriever = self._get_retriever()
        if retriever is None:
            return self._unavailable("search_past_incidents")
        return run_tool(
            "search_past_incidents",
            search_past_incidents,
            retriever,
            self._within(remaining_s),
            **kwargs,
        )

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

    def call(
        self, tool_name: str, remaining_s: float | None = None, /, **kwargs: Any
    ) -> ToolResult[Any]:
        """Dispatch by name against the allowlist; an unknown name is a sanitized error.

        `remaining_s` is positional-only, and that is the whole defence: `kwargs` is what a model
        asked for, so a named parameter here could be bound by an argument the model chose. Keeping
        it out of the keyword space means a request naming it lands in `kwargs`, where it is refused
        like any other argument the capability does not declare.
        """
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
        return fn(remaining_s, **kwargs)
