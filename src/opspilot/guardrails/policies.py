"""Executable guardrails — promoted into code now, not deferred to a later "security phase".

Two policies enforced on the connected slice:
  * no unsupported hypothesis — a hypothesis must cite at least one evidence reference that was
    actually produced by a tool during this run (nothing invented).
  * read-only tool policy — the diagnostic loop may call only registered read-only tools.
"""

from __future__ import annotations

from opspilot.tools import CAPABILITY_NAMES


def is_read_only(tool: str) -> bool:
    """The registered capability inventory is the read-only surface. A capability absent from it
    cannot be called, so a mutating one is unreachable by construction rather than by a second
    list somebody has to remember to update."""
    return tool in CAPABILITY_NAMES


def unsupported_citations(citations: list[str], produced_refs: set[str]) -> list[str]:
    """Citations that were NOT produced by a tool this run."""
    return [c for c in citations if c not in produced_refs]


def hypothesis_supported(citations: list[str], produced_refs: set[str]) -> tuple[bool, list[str]]:
    """Supported only if it cites >=1 ref and every citation was produced this run."""
    if not citations:
        return False, ["hypothesis has no supporting citations"]
    violations = unsupported_citations(citations, produced_refs)
    return (not violations), violations
