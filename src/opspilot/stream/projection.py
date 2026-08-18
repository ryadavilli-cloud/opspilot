"""Activity projection, built from the same facts telemetry records.

`emit()` is the single call site that keeps the two honest: it opens the span and builds the
matching activity event from the identical explicit arguments, in one call, so the feed and the
trace cannot drift apart. There is no parameter through which a span's raw attributes, or any other
untrusted content, could reach the projected event. Every field is a plain string the caller states,
the same way it states what telemetry records.

The sequence is supplied by the caller from what the investigation has already emitted, rather than
held in a counter object. One investigation's events are one list, so its position in that list is
the sequence, and there is no second piece of state to keep in step with it.
"""

from __future__ import annotations

from opspilot.obs import tracing
from opspilot.stream.contracts import ActivityEvent


def emit(
    name: str,
    investigation_id: str,
    incident_id: str,
    *,
    sequence: int,
    phase: str,
    action: str,
    detail: str,
    status: str = "ok",
    capability: str | None = None,
    transport: str | None = None,
    outcome: str | None = None,
    references: list[str] | None = None,
) -> ActivityEvent:
    """Record one instrumentation fact as both a telemetry span and its matching activity event."""
    with tracing.span(
        name,
        trace_id=investigation_id,
        attributes={
            "investigation_id": investigation_id,
            "incident_id": incident_id,
            "phase": phase,
            "action": action,
            "status": status,
        },
    ):
        pass
    return ActivityEvent(
        sequence=sequence,
        phase=phase,
        action=action,
        status=status,
        detail=detail,
        capability=capability,
        transport=transport,
        outcome=outcome,
        references=list(references or []),
    )
