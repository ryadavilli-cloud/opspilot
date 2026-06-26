"""Stubbed investigation tools (Phase 1). Real implementations land Phase 3+.

These return canned, well-shaped results so the graph flows end-to-end before any real
retrieval or telemetry exists.
"""

from __future__ import annotations

from opspilot.state import Evidence


def search_runbooks(query: str) -> list[Evidence]:
    return [
        {"source": "runbook", "ref": "RB-STUB-001", "content": f"(stub) runbook hit for: {query}"}
    ]


def search_past_incidents(query: str) -> list[Evidence]:
    return [
        {
            "source": "past_incident",
            "ref": "INC-STUB-042",
            "content": f"(stub) similar incident for: {query}",
        }
    ]
