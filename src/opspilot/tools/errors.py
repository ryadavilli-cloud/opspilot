"""Uniform envelope assembly: validate, time, cap, sanitize. No exception escapes a tool.

`run_tool` is the single boundary every tool goes through, and therefore the one place that
translates what happened into the two axes. Provider-shaped failure never travels further: a
validation failure is `rejected`, an error inside the tool's own logic is `failed`, and a source
that could not be reached is `unavailable`, reported by the caller that discovered it.

The completeness axis is assigned here too, and only for a successful run: capped results are
`partial` because the unseen remainder could change the picture, no results at all is `empty`
because the source answered authoritatively with nothing, and everything else is `complete`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from opspilot.obs.tracing import span
from opspilot.tools.contracts import (
    MAX_RESULTS,
    Completeness,
    ExecutionOutcome,
    ToolMetadata,
    ToolResult,
)


def sanitize(exc: Exception) -> str:
    """A short, caller-safe message. Validation errors are summarized; nothing else is detailed."""
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ())) or "input"
            parts.append(f"{loc}: {err.get('msg', 'invalid')}")
        return "invalid request — " + "; ".join(parts)
    return "invalid request"


def _metadata(tool_name: str, started: float, count: int, truncated: bool = False) -> ToolMetadata:
    return ToolMetadata(
        tool_name=tool_name,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        result_count=count,
        truncated=truncated,
    )


def error_result(
    tool_name: str,
    message: str,
    started: float,
    outcome: ExecutionOutcome = ExecutionOutcome.FAILED,
) -> ToolResult[Any]:
    """A non-answering result. The caller names which way it failed; nothing defaults to a value
    that would let an unreachable source read as an ordinary error."""
    return ToolResult(
        tool_name=tool_name,
        outcome=outcome,
        completeness=Completeness.NOT_APPLICABLE,
        error=message,
        metadata=_metadata(tool_name, started, 0),
    )


def _fail(
    sp: Any, tool_name: str, message: str, started: float, outcome: ExecutionOutcome
) -> ToolResult[Any]:
    """Close the span with both axes and return the non-answering envelope."""
    sp.status = "error"
    sp.attributes["execution_outcome"] = outcome.value
    sp.attributes["completeness"] = Completeness.NOT_APPLICABLE.value
    return error_result(tool_name, message, started, outcome)


def run_tool(
    tool_name: str,
    request_cls: type[BaseModel],
    logic: Callable[[Any], tuple[list, list[str]]],
    **kwargs: Any,
) -> ToolResult[Any]:
    started = time.perf_counter()
    # One tool span at the boundary every tool goes through (Stage 5g / §23), nested under the
    # current node span via the trace context. The result's status is reflected onto the span; no
    # exception crosses the boundary, so the span always closes with a real status.
    with span(f"tool.{tool_name}", attributes={"tool_name": tool_name}) as sp:
        try:
            request = request_cls(**kwargs)
        except ValidationError as exc:
            return _fail(sp, tool_name, sanitize(exc), started, ExecutionOutcome.REJECTED)
        except Exception:  # noqa: BLE001 — no exception may cross the boundary, even from a validator
            return _fail(sp, tool_name, "invalid request", started, ExecutionOutcome.REJECTED)
        try:
            records, evidence_refs = logic(request)
        except Exception:  # noqa: BLE001 — no exception may cross the tool boundary
            return _fail(sp, tool_name, "internal tool error", started, ExecutionOutcome.FAILED)

        truncated = len(records) > MAX_RESULTS
        records = records[:MAX_RESULTS]
        if truncated:
            completeness = Completeness.PARTIAL
        elif records:
            completeness = Completeness.COMPLETE
        else:
            completeness = Completeness.EMPTY

        sp.attributes["execution_outcome"] = ExecutionOutcome.SUCCEEDED.value
        sp.attributes["completeness"] = completeness.value
        sp.attributes["result_count"] = len(records)
        return ToolResult(
            tool_name=tool_name,
            outcome=ExecutionOutcome.SUCCEEDED,
            completeness=completeness,
            results=records,
            evidence_refs=evidence_refs[: len(records)] if truncated else evidence_refs,
            metadata=_metadata(tool_name, started, len(records), truncated),
        )
