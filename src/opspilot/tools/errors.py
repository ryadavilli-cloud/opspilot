"""Uniform envelope assembly: validate, time, cap, sanitize. No exception escapes a tool.

`run_tool` is the single boundary every capability goes through, and therefore the one place that
translates what happened into the two axes. Provider-shaped failure never travels further: a
request that does not fit the capability's parameters is `rejected`, an error inside the
capability's own logic is `failed`, and a source that could not be reached is `unavailable`, raised
as `SourceUnavailable` by the source itself, so an unreachable container cannot present as a defect
in the capability that queried it.

`validated` is how a capability's typed parameters become its validation. The implementation
declares what it takes; the decorator checks and coerces what a caller supplied against those
annotations, and a mismatch, a missing argument, or an unknown one raises before the body runs. A
capability therefore has no request model of its own: its parameter list is the contract. Only
that check can reject: a record the capability could not build from a row it read is a defect
here, not a bad request.

The completeness axis is assigned here too, and only for a successful run: capped results are
`partial` because the unseen remainder could change the picture, no results at all is `empty`
because the source answered authoritatively with nothing, and everything else is `complete`.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from pydantic import ConfigDict, ValidationError, validate_call

from opspilot.data.operational_records import SourceTimedOut, SourceUnavailable
from opspilot.data.structured_query import QueryRejected
from opspilot.obs.tracing import span
from opspilot.tools.contracts import (
    MAX_RESULTS,
    Completeness,
    ExecutionOutcome,
    RequestRejected,
    SourceRowMismatch,
    ToolMetadata,
    ToolResult,
)

# `arbitrary_types_allowed` covers the injected source, which is a constructed collaborator rather
# than a caller argument; every other parameter is a value a caller supplied and is checked against
# its annotation.
_check_arguments = validate_call(config=ConfigDict(arbitrary_types_allowed=True))


def validated[**P, R](implementation: Callable[P, R]) -> Callable[P, R]:
    """Turn a capability's typed parameters into its request validation.

    It also fixes where a validation failure came from, which the exception type alone cannot say.
    The arguments are checked before the body is entered, so anything pydantic raises once inside
    is about stored data rather than about the request, and is re-raised as such. Doing it here
    rather than by inspecting the error keeps the two apart structurally, and holds for concurrent
    investigations because nothing is remembered between calls.
    """

    @functools.wraps(implementation)
    def body(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return implementation(*args, **kwargs)
        except ValidationError as exc:
            raise SourceRowMismatch(implementation.__name__) from exc

    return _check_arguments(body)


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


def run_tool[T](
    tool_name: str,
    implementation: Callable[..., tuple[list[T], list[str]]],
    *source: Any,
    **kwargs: Any,
) -> ToolResult[T]:
    """Run one capability and wrap what it returns, or what happened instead, in the envelope.

    `source` is what deterministic code injects (the records reader or the retriever, and the
    deadline that bounds the call); `kwargs` is what the caller asked for. Only the second is
    validated against the implementation's annotations, and only the second can be rejected.
    """
    started = time.perf_counter()
    # One tool span at the boundary every capability goes through, nested under the current span via
    # the trace context. The result's status is reflected onto the span; no exception crosses the
    # boundary, so the span always closes with a real status.
    with span(f"tool.{tool_name}", attributes={"tool_name": tool_name}) as sp:
        try:
            records, evidence_refs = implementation(*source, **kwargs)
        except ValidationError as exc:
            return _fail(sp, tool_name, sanitize(exc), started, ExecutionOutcome.REJECTED)
        except (RequestRejected, QueryRejected) as exc:
            # Refused before execution, so nothing ran: `rejected`, exactly as an unknown capability
            # is. Reporting it as an empty success would answer a question that was never asked.
            # The message is this codebase's own text, never a provider's.
            return _fail(sp, tool_name, str(exc), started, ExecutionOutcome.REJECTED)
        except SourceTimedOut:
            # Reachable and answering, but not within the time this call was given. Distinct from
            # unavailable because the same question asked over a narrower scope may still be
            # answerable, which is not true of a source that is down.
            return _fail(sp, tool_name, "source timed out", started, ExecutionOutcome.TIMED_OUT)
        except SourceUnavailable:
            # The source did not answer. Reported apart from `failed` so the question this
            # capability was asked stays open rather than reading as a defect in the code that
            # asked it. The provider's own message never travels with it.
            return _fail(sp, tool_name, "source unavailable", started, ExecutionOutcome.UNAVAILABLE)
        except SourceRowMismatch:
            # The source answered and the row did not fit this capability's record. Neither the
            # request nor the source's availability was at fault, so it is a defect to fix here.
            return _fail(sp, tool_name, "internal tool error", started, ExecutionOutcome.FAILED)
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
