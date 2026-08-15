"""Executable guardrails — promoted into code now, not deferred to a later "security phase".

One policy remains here: the read-only tool boundary. Citation grounding, the second policy this
module used to hold, is superseded by the four-check grounding gate (`grounding/checks.py`); the
old graph path's `safety_validate` now delegates to that gate's reference-resolution primitive
directly rather than through a policy defined here.
"""

from __future__ import annotations

from opspilot.tools import CAPABILITY_NAMES


def is_read_only(tool: str) -> bool:
    """The registered capability inventory is the read-only surface. A capability absent from it
    cannot be called, so a mutating one is unreachable by construction rather than by a second
    list somebody has to remember to update."""
    return tool in CAPABILITY_NAMES
