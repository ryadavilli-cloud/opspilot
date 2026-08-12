"""The governed structured-query capability.

One capability like any other: it validates a request, executes read-only under a limit and a
deadline, and returns the two-axis envelope. What differs is the request, which is a bounded
structure rather than a flat parameter set, and the fact that validation can refuse it before
anything executes (`system-design.md` §8.2).

A refusal is `rejected`, never an empty result. The two would read identically to anything counting
rows, and they mean opposite things: one says the question was never asked, the other says the
scope holds nothing. Admission turns the first into a limitation naming the question it failed to
answer.

The grant is separate from the approved surface. The surface is what could ever be read; the grant
is what this request was allowed, and it is supplied by deterministic code rather than named in the
structure, because a request that could widen its own grant would not be a grant.
"""

from __future__ import annotations

from typing import Any

from opspilot.data.operational_records import OperationalRecords
from opspilot.data.structured_query import (
    APPROVED_SURFACE,
    StructuredQuery,
    validate,
)
from opspilot.tools.contracts import ToolResult
from opspilot.tools.errors import run_tool

# Every approved collection, for a caller that holds no narrower grant of its own.
ALL_COLLECTIONS = frozenset(APPROVED_SURFACE)


def structured_query(
    records: OperationalRecords,
    *,
    deadline_s: float,
    granted: frozenset[str] = ALL_COLLECTIONS,
    **kwargs: Any,
) -> ToolResult[Any]:
    def logic(request: StructuredQuery) -> tuple[list[Any], list[str]]:
        # Before execution, always. A structure that reaches the source and is refused there has
        # already spent the read this path exists to bound.
        validate(request, granted)
        rows = records.structured(request, deadline_s=deadline_s)
        # A count answers with one number, and it is an observation about the scope rather than a
        # row within it. It carries no evidence reference for the same reason: there is no
        # individual record for a citation to resolve to.
        if request.aggregate == "count":
            return [{"count": int(rows[0]) if rows else 0}], []
        return list(rows), []

    return run_tool("structured_query", StructuredQuery, logic, **kwargs)
