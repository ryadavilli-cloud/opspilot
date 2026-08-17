"""The emission seam emits OTLP-shaped spans under the parent trace_id, and the node
wrapper traces every dispatch with no per-node code. A missing/broken trace is a silent failure
exactly when it is needed, so this is tested, not asserted (code-guidelines §23)."""

from __future__ import annotations

import pytest

from opspilot.obs import tracing


class _State:
    """Minimal state stand-in carrying the correlation ids the standard attribute set reads."""

    def __init__(self, **kw: object) -> None:
        self.investigation_id = kw.get("investigation_id", "inv-1")
        self.incident_id = kw.get("incident_id", "inc-004")
        self.workflow_version = kw.get("workflow_version", "1.0")
        self.trace_id = kw.get("trace_id", "")
        self.turn_id = kw.get("turn_id", "")


def test_standard_attributes_reads_turn_id(span_exporter: tracing.InMemorySpanExporter):
    # S-1: turn_id is new on every span. Absent from a state that carries none, it reads as "".
    with_turn = tracing.standard_attributes(_State(turn_id="turn-1"))
    assert with_turn["turn_id"] == "turn-1"

    without_turn = tracing.standard_attributes(_State())
    assert without_turn["turn_id"] == ""


def test_span_emitted_with_standard_attributes(span_exporter: tracing.InMemorySpanExporter):
    with tracing.span("unit", trace_id="t-1", attributes={"node": "diagnose", "k": "v"}) as sp:
        assert sp.trace_id == "t-1"
    assert len(span_exporter.spans) == 1
    got = span_exporter.spans[0]
    assert got.name == "unit" and got.trace_id == "t-1" and got.status == "ok"
    assert got.attributes["node"] == "diagnose"
    assert "latency_ms" in got.attributes and got.attributes["latency_ms"] >= 0.0


def test_nested_spans_link_to_parent(span_exporter: tracing.InMemorySpanExporter):
    with tracing.span("parent", trace_id="t-1"):
        with tracing.span("child", trace_id="t-1"):
            pass
    by_name = {s.name: s for s in span_exporter.spans}
    assert by_name["parent"].parent_span_id is None
    assert by_name["child"].parent_span_id == by_name["parent"].span_id


def test_span_status_error_on_exception_and_reraises(span_exporter: tracing.InMemorySpanExporter):
    with pytest.raises(ValueError):
        with tracing.span("boom", trace_id="t-1"):
            raise ValueError("nope")
    assert span_exporter.spans[0].status == "error"


def test_traced_node_emits_span_per_dispatch(span_exporter: tracing.InMemorySpanExporter):
    calls: list[str] = []

    def fake_node(state: object) -> dict[str, object]:
        calls.append("ran")
        return {"result": "ok"}

    wrapped = tracing.traced_node("diagnose", fake_node)
    out = wrapped(_State(trace_id="inv-1"))

    assert out == {"result": "ok"} and calls == ["ran"]  # behaviour unchanged
    span = span_exporter.spans[0]
    assert span.name == "node.diagnose" and span.trace_id == "inv-1"
    assert span.attributes["node"] == "diagnose"
    assert span.attributes["investigation_id"] == "inv-1"
    assert span.attributes["incident_id"] == "inc-004"
    assert span.attributes["workflow_version"] == "1.0"


def test_traced_node_falls_back_to_investigation_id(span_exporter: tracing.InMemorySpanExporter):
    # Before trace_id is explicitly set, the wrapper uses investigation_id as the correlation id.
    wrapped = tracing.traced_node("ingest", lambda s: {})
    wrapped(_State(investigation_id="inv-9", trace_id=""))
    assert span_exporter.spans[0].trace_id == "inv-9"


def test_traced_node_forwards_config_to_config_taking_nodes(span_exporter):
    # LangGraph injects `config` (carrying the per-run ToolService) into nodes that declare it.
    # The wrapper MUST forward it — dropping it silently breaks dependency injection.
    seen: dict[str, object] = {}

    def node_with_config(state: object, config: object = None) -> dict[str, object]:
        seen["config"] = config
        return {}

    tracing.traced_node("triage", node_with_config)(_State(), {"configurable": {"svc": "boom"}})
    assert seen["config"] == {"configurable": {"svc": "boom"}}


def test_traced_node_does_not_pass_config_to_state_only_nodes():
    # A node declaring only (state) must not receive an unexpected positional config.
    def state_only(state: object) -> dict[str, object]:
        return {"ok": True}

    assert tracing.traced_node("ingest", state_only)(_State(), {"configurable": {}}) == {"ok": True}


def test_tool_span_nests_under_node_and_inherits_trace(span_exporter):
    from opspilot.tools.errors import run_tool, validated

    @validated
    def _capability(source: str, deadline_s: float, *, x: int = 0) -> tuple[list[dict], list[str]]:
        return [{"a": x}], ["metrics:m-1"]

    with tracing.span("node.diagnose", trace_id="t-9"):
        run_tool("get_metrics", _capability, "source", 1.0, x=1)

    tool = next(s for s in span_exporter.spans if s.name == "tool.get_metrics")
    node = next(s for s in span_exporter.spans if s.name == "node.diagnose")
    assert tool.trace_id == "t-9"  # inherited from the node via the trace context
    assert tool.parent_span_id == node.span_id  # nested under the node span
    assert tool.attributes["tool_name"] == "get_metrics"
    assert tool.attributes["execution_outcome"] == "succeeded"
    assert tool.attributes["completeness"] == "complete"
    assert tool.attributes["result_count"] == 1


def test_model_span_captures_usage(span_exporter):
    from opspilot.llm.base import ChatMessage, ChatResult
    from opspilot.llm.client import TracedChatModel

    class _Model:
        model_id = "gpt-5-mini"

        def complete(self, messages, *, temperature=0.0):
            return ChatResult(
                text="ok",
                model_id="gpt-5-mini",
                finish_reason="stop",
                usage={"prompt_tokens": 12, "completion_tokens": 5},
            )

    with tracing.span("node.diagnose", trace_id="t-9"):
        TracedChatModel(_Model()).complete([ChatMessage("user", "hi")])

    model = next(s for s in span_exporter.spans if s.name == "model.complete")
    assert model.trace_id == "t-9" and model.attributes["model_deployment"] == "gpt-5-mini"
    assert model.attributes["tokens_in"] == 12 and model.attributes["tokens_out"] == 5


def test_traced_node_reflects_error_onto_span(span_exporter: tracing.InMemorySpanExporter):
    wrapped = tracing.traced_node(
        "escalate", lambda s: {"degraded": True, "error": "budget exhausted"}
    )
    wrapped(_State())
    span = span_exporter.spans[0]
    assert span.status == "error"
    # the escalation reason is now on the span, not only in the API response
    assert span.attributes["reason"] == "budget exhausted"
