"""Turn and investigation identity: the correlation ids no component owned before this module
(status.md 10.12).

`data-and-evidence.md` §3 fixes exactly two identities that matter here: investigation identity
("one incident under study") and turn identity ("one bounded cycle within an investigation"). A
live session carries no identity of its own, it is the ephemeral conversational surface over an
investigation, read from the investigation and its completed turns, and is not represented here.

No persistence exists yet (a completed-turn artifact and durability across turns both come later),
so an investigation exists only for the lifetime of the one turn that opens it. Both ids are minted
together for that reason, this is not yet the durable, multi-turn investigation later work builds.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class TurnIdentity:
    """The two real identities one turn carries, plus the business incident id it investigates."""

    turn_id: str
    investigation_id: str
    incident_id: str


def start_turn(incident_id: str) -> TurnIdentity:
    """Mint a new turn's identity pair for a turn beginning against `incident_id`."""
    return TurnIdentity(
        turn_id=_new_id("turn"),
        investigation_id=_new_id("inv"),
        incident_id=incident_id,
    )
