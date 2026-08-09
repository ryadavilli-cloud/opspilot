"""S-1: activity projection is produced at the same instrumentation point as telemetry, from the
same recorded facts, and can carry nothing telemetry does not also record (code-guidelines §11)."""

from __future__ import annotations

from opspilot.obs import tracing
from opspilot.stream.contracts import ActivityEvent
from opspilot.stream.projection import ActivityProjector, emit
from opspilot.turn.identity import start_turn


def test_emit_produces_a_span_and_the_matching_activity_event(
    span_exporter: tracing.InMemorySpanExporter,
):
    turn = start_turn(incident_id="inc-001")
    projector = ActivityProjector()

    event = emit(
        "turn.phase_change",
        turn,
        projector,
        phase="investigating",
        action="gather evidence",
        detail="Investigation started.",
    )

    assert isinstance(event, ActivityEvent)
    assert event.phase == "investigating"
    assert event.action == "gather evidence"
    assert event.status == "ok"
    assert event.sequence == 1

    sp = span_exporter.spans[0]
    assert sp.trace_id == turn.turn_id
    assert sp.attributes["turn_id"] == turn.turn_id
    assert sp.attributes["investigation_id"] == turn.investigation_id
    assert sp.attributes["phase"] == "investigating"
    assert sp.attributes["action"] == "gather evidence"


def test_activity_projector_assigns_sequence_positions_in_order():
    projector = ActivityProjector()
    first = projector.project(phase="investigating", action="a", status="ok", detail="first")
    second = projector.project(phase="investigating", action="b", status="ok", detail="second")
    third = projector.project(phase="synthesizing", action="c", status="ok", detail="third")
    assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)


def test_activity_event_carries_only_explicit_fields_no_stream_only_facts():
    # The projection can never state more than what was explicitly recorded: there is no
    # parameter through which arbitrary span attributes, prompts, or secrets could reach it.
    projector = ActivityProjector()
    event = projector.project(
        phase="investigating", action="query metrics", status="ok", detail="Queried metrics."
    )
    dumped = event.model_dump()
    assert set(dumped) == {
        "event_type",
        "sequence",
        "phase",
        "action",
        "status",
        "detail",
        "capability",
        "transport",
        "outcome",
        "references",
    }
    assert dumped["capability"] is None
    assert dumped["references"] == []


def test_emit_two_turns_get_independent_sequences(span_exporter: tracing.InMemorySpanExporter):
    # Turn isolation: one projector per turn, never shared.
    turn_a = start_turn(incident_id="inc-001")
    turn_b = start_turn(incident_id="inc-002")
    projector_a = ActivityProjector()
    projector_b = ActivityProjector()

    event_a1 = emit("t", turn_a, projector_a, phase="p", action="a", detail="d")
    event_b1 = emit("t", turn_b, projector_b, phase="p", action="a", detail="d")
    event_a2 = emit("t", turn_a, projector_a, phase="p", action="a", detail="d")

    assert event_a1.sequence == 1
    assert event_b1.sequence == 1
    assert event_a2.sequence == 2

    trace_ids = {sp.trace_id for sp in span_exporter.spans}
    assert trace_ids == {turn_a.turn_id, turn_b.turn_id}
