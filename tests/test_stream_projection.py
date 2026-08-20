"""Activity projection: one call, one span, one event, from the same stated facts.

The reason this is one function rather than two calls a caller makes in sequence is that two calls
drift. A feed entry telemetry cannot corroborate, or a span with no matching entry, is exactly the
kind of gap that only shows up when someone is trying to explain a bad run after the fact.
"""

from __future__ import annotations

from opspilot.obs import tracing
from opspilot.stream.projection import emit


def _emit(sequence: int = 1, **overrides):
    fields = dict(
        phase="gathering",
        action="query_logs",
        detail="query_logs: succeeded, complete (3 admitted)",
        capability="query_logs",
        transport="direct",
        outcome="succeeded",
        references=["logs:checkout-api:evt-1"],
    )
    fields.update(overrides)
    return emit("investigation.capability", "inv-1", "inc-005", sequence=sequence, **fields)


def test_one_call_produces_both_the_span_and_the_matching_event(span_exporter):
    event = _emit()

    span = next(s for s in span_exporter.spans if s.name == "investigation.capability")
    assert span.attributes["investigation_id"] == "inv-1"
    assert span.attributes["incident_id"] == "inc-005"
    assert span.attributes["phase"] == event.phase
    assert span.attributes["action"] == event.action
    assert span.attributes["status"] == event.status


def test_the_event_carries_what_the_compact_feed_consumes(span_exporter):
    event = _emit()

    assert event.sequence == 1
    assert event.capability == "query_logs"
    assert event.transport == "direct"
    assert event.outcome == "succeeded"
    assert event.references == ["logs:checkout-api:evt-1"]


def test_the_span_is_correlated_by_the_investigation_alone(span_exporter):
    """One identity on the wire and one in telemetry, so a run is queryable by the identifier the
    client was given without joining anything first."""
    _emit()

    span = next(s for s in span_exporter.spans if s.name == "investigation.capability")
    assert span.trace_id == "inv-1"
    assert "turn_id" not in span.attributes


def test_an_error_status_travels_to_both(span_exporter):
    event = _emit(status="error", detail="proposal refused", capability=None, transport=None)

    span = next(s for s in span_exporter.spans if s.name == "investigation.capability")
    assert event.status == "error"
    assert span.attributes["status"] == "error"


def test_nesting_puts_the_activity_span_under_the_investigation(span_exporter):
    with tracing.span("investigation", trace_id="inv-1"):
        _emit()

    by_name = {s.name: s for s in span_exporter.spans}
    assert by_name["investigation.capability"].parent_span_id == by_name["investigation"].span_id


def test_the_span_carries_what_the_event_carries():
    """Both are built here from the same facts, so a span given fewer of them is a drift of its
    own. The capability, the transport it arrived on, and how it ended are what a hosted trace is
    queried by, and they were reaching the client's feed while the telemetry got neither."""
    exporter = tracing.InMemorySpanExporter()
    previous = tracing.get_exporter()
    tracing.configure_exporter(exporter)
    try:
        event = emit(
            "investigation.capability",
            "inv-1",
            "inc-005",
            sequence=1,
            phase="gathering",
            action="query_logs",
            detail="query_logs: succeeded",
            capability="query_logs",
            transport="direct",
            outcome="succeeded",
            references=["logs:checkout-api:1", "logs:checkout-api:2"],
        )
    finally:
        tracing.configure_exporter(previous)

    span = exporter.spans[-1]
    assert span.attributes["capability"] == event.capability == "query_logs"
    assert span.attributes["transport"] == event.transport == "direct"
    assert span.attributes["outcome"] == event.outcome == "succeeded"
    assert span.attributes["reference_count"] == "2"


def test_an_attribute_nothing_supplied_is_absent_rather_than_empty():
    """A query has to tell an entry that had no transport from one whose transport was lost."""
    exporter = tracing.InMemorySpanExporter()
    previous = tracing.get_exporter()
    tracing.configure_exporter(exporter)
    try:
        emit(
            "investigation.objective",
            "inv-1",
            "inc-005",
            sequence=1,
            phase="objective",
            action="objective set",
            detail="establish why latency rose",
        )
    finally:
        tracing.configure_exporter(previous)

    attributes = exporter.spans[-1].attributes
    assert "transport" not in attributes
    assert "capability" not in attributes
    assert "outcome" not in attributes
