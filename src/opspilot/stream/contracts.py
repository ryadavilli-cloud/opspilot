"""The stream envelope: identity first, activity as it happens, then one terminal event.

One `investigation_id` correlates everything, so there is one identity on the wire and one in
telemetry. A client never assembles state from the activity feed: the brief arrives whole, in the
terminal event, and that event is the only thing that ends the stream.

The terminal event is either a delivery or a failure, never both and never neither. A stream that
stopped without one was abandoned, which is a different thing from an investigation that finished,
and the difference has to survive to the client.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opspilot.assessment.contracts import Brief


class IdentityEvent(BaseModel):
    """The stream's first event: which investigation this is, and nothing else."""

    model_config = ConfigDict(frozen=True)

    event_type: Literal["identity"] = "identity"
    investigation_id: str


class ActivityEvent(BaseModel):
    """One activity entry: which agent or capability acted, what it did, and what it obtained.

    Produced at the same instrumentation point as the telemetry span it mirrors, from the same
    stated facts. Never carries a prompt, hidden reasoning, provider-shaped content, or a secret.
    """

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


class TerminalEvent(BaseModel):
    """How the investigation ended: the brief it delivered, or the category it failed under.

    A failure carries no brief by construction. A failed execution persists nothing and concludes
    nothing, so there is no brief for it to carry, and a shape that allowed one would invite
    delivering something that was never grounded.
    """

    model_config = ConfigDict(frozen=True)

    event_type: Literal["terminal"] = "terminal"
    investigation_id: str
    brief: Brief | None = None
    failure: str | None = None

    @model_validator(mode="after")
    def _delivered_or_failed(self) -> TerminalEvent:
        if (self.brief is None) == (self.failure is None):
            raise ValueError("a terminal event carries either a brief or a failure category")
        return self


StreamEvent = Annotated[
    IdentityEvent | ActivityEvent | TerminalEvent,
    Field(discriminator="event_type"),
]
