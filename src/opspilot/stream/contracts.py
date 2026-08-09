"""The stream envelope: identities-first, activity entries, then a close marker.

`runtime-and-deployment.md` §2 fixes the ordering: the streaming request emits the investigation
and turn identities as its first event, then activity as it happens. `system-design.md` §10.4 fixes
the activity event's field set. This closing event is a transport-demonstration marker only, not a
completed-turn outcome; accepted outcomes (complete/partial/inconclusive) do not exist yet.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class IdentityEvent(BaseModel):
    """The stream's first event: the investigation and turn identities, and nothing else."""

    model_config = ConfigDict(frozen=True)

    event_type: Literal["identity"] = "identity"
    turn_id: str
    investigation_id: str


class ActivityEvent(BaseModel):
    """One activity entry, the exact field set `system-design.md` §10.4 fixes. Carries only what
    the compact feed consumes, produced at the same instrumentation point as the telemetry span it
    mirrors. Never carries a prompt, hidden reasoning, provider-shaped content, or a secret."""

    model_config = ConfigDict(frozen=True)

    event_type: Literal["activity"] = "activity"
    sequence: int
    phase: str
    action: str
    status: str
    detail: str
    capability: str | None = None
    transport: str | None = None
    outcome: str | None = None
    references: list[str] = Field(default_factory=list)


class StreamCloseMarker(BaseModel):
    """The stream's closing event. A transport-ordering proof only, not a completed-turn outcome."""

    model_config = ConfigDict(frozen=True)

    event_type: Literal["close"] = "close"
    turn_id: str


StreamEvent = Annotated[
    IdentityEvent | ActivityEvent | StreamCloseMarker,
    Field(discriminator="event_type"),
]
