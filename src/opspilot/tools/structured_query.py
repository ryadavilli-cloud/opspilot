"""The governed structured-query capability.

One capability like any other: it validates a request, executes read-only under a limit and a
deadline, and returns the two-axis envelope. What differs is the request, which is a bounded
structure rather than a flat parameter set, and the fact that validation can refuse it before
anything executes.

A refusal is `rejected`, never an empty result. The two would read identically to anything counting
rows, and they mean opposite things: one says the question was never asked, the other says the
scope holds nothing. Admission turns the first into a limitation naming the question it failed to
answer.

The grant is separate from the approved surface. The surface is what could ever be read; the grant
is what this request was allowed. It is supplied positionally by deterministic code rather than
named in the structure, because a request that could widen its own grant would not be a grant.

Every row carries the reference of the record it projects. That reference is formed from the row's
own identifying fields, so each projection is widened to include them before the query is
translated: a row an assessment cannot cite is a row it cannot use. A count projects no row at all,
so it carries no row reference; admission makes it citable by the operation that produced it.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from opspilot.data.operational_records import OperationalRecords
from opspilot.data.structured_query import (
    APPROVED_SURFACE,
    StructuredQuery,
    validate,
)

# Every approved collection, for a caller that holds no narrower grant of its own.
ALL_COLLECTIONS = frozenset(APPROVED_SURFACE)

# Each approved collection's reference prefix and the identifying fields that compose it. The same
# record reached through a dedicated capability carries the same reference, which is what makes the
# two paths cite one thing rather than two.
ROW_REFERENCES: Mapping[str, tuple[str, tuple[str, ...]]] = MappingProxyType(
    {
        "incident": ("incident", ("incident_id",)),
        "deployment": ("deploys", ("service", "deploy_id")),
        "alert": ("alert", ("service", "alert_id")),
    }
)


def structured_query(
    records: OperationalRecords,
    deadline_s: float,
    granted: frozenset[str],
    **structure: Any,
) -> tuple[list[Any], list[str]]:
    """Ask the operational records a question of your own, as a structure this validates."""
    request = StructuredQuery(**structure)
    # Before execution, always. A structure that reaches the source and is refused there has
    # already spent the read this path exists to bound.
    validate(request, granted)

    if request.aggregate == "count":
        # A count answers with one number, and it is an observation about the scope rather than a
        # row within it, so there is no individual record for a row reference to name.
        rows = records.structured(request, deadline_s=deadline_s)
        return [{"count": int(rows[0]) if rows else 0}], []

    prefix, identifying = ROW_REFERENCES[request.collection]
    projection = list(request.projection)
    projection += [name for name in identifying if name not in projection]
    rows = list(
        records.structured(
            request.model_copy(update={"projection": projection}), deadline_s=deadline_s
        )
    )
    refs = [":".join((prefix, *(str(row[name]) for name in identifying))) for row in rows]
    return rows, refs
