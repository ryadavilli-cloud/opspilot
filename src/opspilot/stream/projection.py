"""Activity projection derived from the same instrumentation facts telemetry records.

`code-guidelines.md` §11 (MUST-level): "Activity events MUST be produced at the same instrumentation
points as telemetry, from the same recorded facts, carrying the shared identifiers... Code MUST NOT
emit a stream-only fact that telemetry does not record, generate activity prose with a model call,
or let an event carry prompts, hidden reasoning, provider-shaped content, or secrets."

`emit()` is the single call site that satisfies this: it opens the telemetry span and builds the
matching `ActivityEvent` from the identical explicit facts in one call, so the two can never drift
apart. There is no parameter through which a span's raw attributes, or any other untrusted content,
could reach the projected event, every field is a plain string the caller states explicitly, the
same way it states what telemetry records.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opspilot.obs import tracing
from opspilot.stream.contracts import ActivityEvent
from opspilot.turn.identity import TurnIdentity


@dataclass
class ActivityProjector:
    """Assigns sequence positions for one turn's activity stream. Scoped to one turn, never shared
    across turns or reused after a turn ends."""

    _next_sequence: int = field(default=1)

    def project(
        self,
        *,
        phase: str,
        action: str,
        status: str,
        detail: str,
        capability: str | None = None,
        transport: str | None = None,
        outcome: str | None = None,
        references: list[str] | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            sequence=self._next_sequence,
            phase=phase,
            action=action,
            status=status,
            detail=detail,
            capability=capability,
            transport=transport,
            outcome=outcome,
            references=list(references or []),
        )
        self._next_sequence += 1
        return event


def emit(
    name: str,
    turn: TurnIdentity,
    projector: ActivityProjector,
    *,
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
        trace_id=turn.turn_id,
        attributes={
            "investigation_id": turn.investigation_id,
            "incident_id": turn.incident_id,
            "turn_id": turn.turn_id,
            "phase": phase,
            "action": action,
            "status": status,
        },
    ):
        pass
    return projector.project(
        phase=phase,
        action=action,
        status=status,
        detail=detail,
        capability=capability,
        transport=transport,
        outcome=outcome,
        references=references,
    )
