"""S-1: turn identity is the correlation id no component owned before this slice."""

from __future__ import annotations

from opspilot.turn.identity import start_turn


def test_start_turn_mints_turn_and_investigation_ids():
    turn = start_turn(incident_id="inc-001")
    assert turn.incident_id == "inc-001"
    assert turn.turn_id and turn.turn_id.startswith("turn-")
    assert turn.investigation_id and turn.investigation_id.startswith("inv-")


def test_start_turn_ids_are_unique_per_call():
    first = start_turn(incident_id="inc-001")
    second = start_turn(incident_id="inc-001")
    assert first.turn_id != second.turn_id
    assert first.investigation_id != second.investigation_id


def test_turn_identity_is_frozen():
    turn = start_turn(incident_id="inc-001")
    try:
        turn.turn_id = "tampered"  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised, "TurnIdentity must be immutable once minted"
